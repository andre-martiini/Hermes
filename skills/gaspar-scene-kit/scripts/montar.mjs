#!/usr/bin/env node
// Roteiro de cenas (JSON) → projeto HyperFrames feito só com o kit → lint → MP4.
//
//   node montar.mjs roteiro.json SAIDA              # 9:16 e/ou 16:9 conforme "formato"
//   node montar.mjs roteiro.json SAIDA --so-html    # só gera o projeto e passa o lint (grátis, segundos)
//   node montar.mjs roteiro.json SAIDA --revisao    # + PNG de cada cena assentada em SAIDA/<formato>/revisao
//   node montar.mjs roteiro.json SAIDA --sem-voz    # ignora "narracao" (vídeo mudo, grátis)
//   --sem-trilha --sem-sfx --sem-lut                 # desliga partes da pós (Fase 3)
//   --forcar                                         # renderiza mesmo com gate de legibilidade/legenda falhando
//
// Com "gravacao" (modo sobreposição): o vídeo do André fica no fundo com o som original, a legenda vem da
// fala transcrita (palavra a palavra) e cada cartão entra no topo quando a fala diz o seu "quando".
//
// Com "narracao" nas cenas: voz Aoede (~US$ 0,15/min, com cache) e legendas palavra a palavra alinhadas ao
// roteiro; cada item entra quando a fala o cita, e a cena dura a fala + respiro.
// Saída: SAIDA/<formato>/projeto/index.html, SAIDA/<titulo> (<formato>).mp4 e SAIDA/<formato>/cenas.json
// (tempo de cada cena; os marcadores de SFX ficam em window.__sfx na página).
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { execFileSync, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { TIPOS, duracaoMinima } from "../kit/primitivas.mjs";
import { lint } from "./lint-cena.mjs";
import { medirLoudness, posProduzir, trilhaPadrao } from "./pos.mjs";
import { checkAudio, checkDuracao, checkLegendas, checkLegibilidade, checkLeitura, previa, relatorio } from "./gates.mjs";

const SKILL = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const FPS = 30;
const ENTRADA = 0.45; // = Kit.T.entrada: quanto a cena anterior fica por baixo de um wipe
const DIM = { vertical: [1080, 1920], horizontal: [1920, 1080] };

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// Com voz: a fala de cada cena começa LEAD s depois da cena e termina RESPIRO s antes da próxima.
const LEAD = 0.25;
const RESPIRO = 0.6;
const JUNTAR_MS = { palavra: 300, frase: 1200 };

const norm = (s) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "");

// Instante (s, relativo à cena) em que a fala cita o item: 1ª palavra forte (≥ 4 letras) do item, ou a 1ª.
export function deixa(item, legendas, lead = LEAD) {
  const palavras = String(item).split(/\s+/).map(norm).filter(Boolean);
  const alvo = palavras.find((p) => p.length >= 4) || palavras[0];
  const tok = legendas.find((c) => norm(c.text) === alvo) || legendas.find((c) => alvo && norm(c.text).startsWith(alvo.slice(0, 5)));
  return tok ? lead + tok.startMs / 1000 : null;
}

// Início (s) da 1ª ocorrência da frase na fala, palavras consecutivas; null se não for dita.
export function achar(frase, legendas) {
  const alvo = String(frase).split(/\s+/).map(norm).filter(Boolean);
  if (!alvo.length) return null;
  const fala = legendas.map((c) => norm(c.text));
  for (let i = 0; i + alvo.length <= fala.length; i++)
    if (alvo.every((p, k) => fala[i + k] === p)) return legendas[i].startMs / 1000;
  return null;
}

const itensDaCena = (c) => c.itens?.map((i) => (Array.isArray(i) ? i[0] : i)) || c.etapas || c.linhas || null;

// Sobreposição: cada cartão entra quando a fala diz `quando` (ou em `inicio` s) e fica `duracao` (≥ leitura).
function planejarSobre(roteiro, voz) {
  const avisos = [];
  const cenas = roteiro.cenas.map((c, i) => {
    if (!TIPOS[c.tipo]) throw new Error(`Cartão ${i + 1}: tipo "${c.tipo}" fora do kit.`);
    if (c.inicio == null && !c.quando) throw new Error(`Cartão ${i + 1}: falta "quando" (frase dita) ou "inicio" (s).`);
    const t0 = c.inicio ?? achar(c.quando, voz.legendas);
    if (t0 == null) throw new Error(`Cartão ${i + 1}: a fala não diz "${c.quando}". Use "inicio" (s) ou corrija "quando".`);
    const minimo = duracaoMinima(c);
    const fim = Math.min(t0 + Math.max(c.duracao || 0, minimo), voz.duracao);
    const depois = voz.legendas.filter((tk) => tk.startMs / 1000 >= t0);
    const itens = itensDaCena(c);
    const em = itens && !c.em ? itens.map((it) => { const e = deixa(it, depois, 0); return e == null ? null : +(e - t0).toFixed(3); }) : c.em;
    return { ...c, i, t0: +t0.toFixed(3), fim: +fim.toFixed(3), minimo, em: em?.some((e) => e != null) ? em : undefined };
  });
  cenas.forEach((c, i) => cenas[i + 1] && cenas[i + 1].t0 < c.fim && avisos.push(`cartões ${i + 1} e ${i + 2} se sobrepõem`));
  return Object.assign(cenas, { avisos });
}

export function planejar(roteiro, voz = null) {
  if (roteiro.gravacao) return planejarSobre(roteiro, voz);
  let t = 0;
  const avisos = [];
  const cenas = roteiro.cenas.map((c, i) => {
    if (!TIPOS[c.tipo]) throw new Error(`Cena ${i + 1}: tipo "${c.tipo}" fora do kit (${Object.keys(TIPOS).join(", ")}).`);
    const minimo = duracaoMinima(c);
    const fala = voz?.falas[i]?.segundos || 0;
    const dur = Math.max(c.duracao || 0, minimo, fala ? LEAD + fala + RESPIRO : 0);
    const p = { ...c, i, t0: +t.toFixed(3), fim: +(t + dur).toFixed(3), minimo, fala };
    const itens = itensDaCena(c);
    if (voz && itens && !c.em) {
      const em = itens.map((it) => deixa(it, voz.legendas[i] || []));
      em.forEach((e, k) => e == null && avisos.push(`cena ${i + 1}: a fala não cita "${itens[k]}" (entra em sequência)`));
      if (em.some((e) => e != null)) p.em = em;
    }
    t += dur;
    return p;
  });
  return Object.assign(cenas, { avisos });
}

// Como createTikTokStyleCaptions: a palavra entra na página enquanto começa a menos de `juntarMs` do início dela.
export function paginar(legendas, juntarMs) {
  const paginas = [];
  for (const c of legendas) {
    const pg = paginas.at(-1);
    if (pg && c.startMs - pg.startMs < juntarMs) { pg.tokens.push(c); pg.endMs = c.endMs; }
    else paginas.push({ startMs: c.startMs, endMs: c.endMs, tokens: [c] });
  }
  paginas.forEach((p, k) => { if (paginas[k + 1]) p.endMs = paginas[k + 1].startMs; });
  return paginas;
}

// `trechos`: [[deslocamento em s, legendas]] — um por cena no motion, um só na sobreposição.
function htmlLegendas(trechos, juntarMs) {
  const blocos = [];
  const dados = [];
  trechos.forEach(([off, legendas]) => {
    const paginas = paginar(legendas || [], juntarMs);
    paginas.forEach((pg, k) => {
      const n = dados.length;
      const ini = off + pg.startMs / 1000;
      // Termina quando a próxima página começa (nunca duas na tela); a última do trecho fica 0,15 s a mais.
      const fim = off + (paginas[k + 1] ? pg.endMs : pg.tokens.at(-1).endMs + 150) / 1000;
      blocos.push(`<div id="leg-${n}" class="legenda clip" data-start="${ini.toFixed(3)}" data-duration="${(fim - ini).toFixed(3)}" data-track-index="2">` +
        pg.tokens.map((tk, k) => `<span class="palavra" id="leg-${n}-${k}">${esc(tk.text)}</span>`).join("") + `</div>`);
      dados.push(pg.tokens.map((tk) => [+(off + tk.startMs / 1000).toFixed(3), +(off + tk.endMs / 1000).toFixed(3)]));
    });
  });
  return { html: blocos.join("\n      "), dados };
}

export function gerarHtml(roteiro, formato, imagens = {}, voz = null) {
  const [w, h] = DIM[formato];
  const cenas = planejar(roteiro, voz);
  const sobre = Boolean(roteiro.gravacao);
  const total = sobre ? voz.duracao : cenas.at(-1).fim;
  const fundo = sobre ? `<video id="gravacao" class="clip" src="assets/gravacao.mp4" data-start="0" data-duration="${total}" data-has-audio="true" data-track-index="0"></video>
      ` : "";
  const secao = (c, i) => {
    const sobra = cenas[i + 1]?.transicao === "wipe" ? ENTRADA : 0;
    const classe = !sobre ? "" : c.tipo === "titulo_atras" ? " atras" : c.tipo === "chamada" ? " cta"
      : c.layout === "dividido" ? " dividida" : " sobre";
    return `<section id="cena-${i}" class="cena${classe} clip" data-start="${c.t0}" data-duration="${+(c.fim - c.t0 + sobra).toFixed(3)}" data-track-index="0">` +
      TIPOS[c.tipo].html(c, imagens[i]) + `</section>`;
  };
  // Camadas (ordem do DOM = profundidade): gravação → títulos "atrás" → recorte da pessoa → cartões e legenda.
  const atras = cenas.map((c, i) => (c.tipo === "titulo_atras" ? secao(c, i) : "")).filter(Boolean);
  const frente = cenas.map((c, i) => (c.tipo !== "titulo_atras" ? secao(c, i) : "")).filter(Boolean);
  const pessoa = sobre && voz?.pessoa ? `<video id="pessoa" class="clip" src="assets/pessoa.webm" muted data-start="0" data-duration="${total}" data-track-index="3"></video>` : "";
  const secoes = [fundo + atras.join("\n      "), pessoa, frente.join("\n      ")].filter(Boolean).join("\n      ");
  const audios = voz && !sobre ? cenas.filter((c) => c.fala).map((c) =>
    `<audio id="voz-${c.i}" class="clip" src="assets/voz-${c.i}.wav" data-start="${(c.t0 + LEAD).toFixed(3)}" data-duration="${c.fala}" data-track-index="1"></audio>`).join("\n      ") : "";
  const leg = voz && roteiro.legenda !== false
    ? htmlLegendas(sobre ? [[0, voz.legendas]] : cenas.map((c, i) => [c.t0 + LEAD, voz.legendas[i]]),
      JUNTAR_MS[roteiro.legenda_estilo || (sobre ? "palavra" : "frase")]) : { html: "", dados: [] };
  const dados = {
    cenas: cenas.map((c, i) => ({
      primitiva: TIPOS[c.tipo].primitiva, t0: c.t0, fim: c.fim, em: c.em, valor: c.valor,
      prefixo: c.prefixo, sufixo: c.sufixo, casas: c.casas, transicao: c.transicao, primeira: i === 0 && !sobre,
      layout: c.layout, foco: c.foco,
    })),
    sobre,
    legendas: leg.dados,
  };
  const html = `<!doctype html>
<html lang="pt-BR" data-formato="${formato}"${leg.dados.length ? " data-legenda" : ""}${sobre ? " data-modo=\"sobreposicao\"" : ""}>
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
      ${audios}
      ${leg.html}
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

// Voz: narrar.py (Aoede, com cache) + legendas.py (whisper só para o tempo; o texto é o do roteiro).
// Refaz o alinhamento só quando a narração mudou.
// Recorte da pessoa (para o texto passar atrás dela): HyperFrames remove-background local, com a borda
// afinada (erosão + gama no alfa) para não sobrar o halo da parede clara. Com cache.
function recortarPessoa(video, saida) {
  const destino = join(saida, "pessoa.webm");
  if (existsSync(destino) && statSync(destino).mtimeMs > statSync(video).mtimeMs) return destino;
  const env = { ...process.env, PATH: pathComFfmpeg() };
  const base = join(saida, "pessoa-base.mp4"), bruto = join(saida, "pessoa-bruto.webm");
  execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-i", video, "-an", "-vf", `fps=${FPS}`, "-c:v", "libx264",
    "-crf", "16", "-pix_fmt", "yuv420p", base], { env });
  if (!existsSync(bruto)) hyperframes(["remove-background", base, "-o", bruto, "--quality", "best"], saida, env);
  execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-c:v", "libvpx-vp9", "-i", bruto, "-filter_complex",
    "[0:v]format=rgba,split[c][a];[a]alphaextract,erosion,lut=y='pow(val/255\\,2.2)*255',gblur=sigma=0.8[m];[c][m]alphamerge",
    "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "6M", "-auto-alt-ref", "0", destino], { env });
  return destino;
}

// Sobreposição ("gravacao" no roteiro): a legenda vem da fala transcrita, e a duração é a da gravação.
function prepararVoz(arq, saida, flags) {
  const roteiro = JSON.parse(readFileSync(arq, "utf8"));
  const py = process.env.GASPAR_PY || join(homedir(), ".tutorial-sistema", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const rodar = (script, ...a) => execFileSync(py, [join(SKILL, "scripts", script), ...a], { stdio: ["ignore", "inherit", "inherit"] });
  if (roteiro.gravacao) {
    const video = resolve(dirname(resolve(arq)), roteiro.gravacao);
    const legArq = join(saida, "legendas.json");
    if (!existsSync(legArq) || statSync(legArq).mtimeMs < statSync(video).mtimeMs)
      rodar("legendas.py", "fala", video, saida, ...(roteiro.chaves ? ["--chaves", roteiro.chaves.join(",")] : []));
    const dur = execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
      { env: { ...process.env, PATH: pathComFfmpeg() } }).toString().trim();
    return { video, duracao: +(+dur).toFixed(3), legendas: JSON.parse(readFileSync(legArq, "utf8")),
      pessoa: roteiro.cenas.some((c) => c.tipo === "titulo_atras") ? recortarPessoa(video, saida) : null };
  }
  if (flags.includes("--sem-voz") || !roteiro.cenas.some((c) => c.narracao)) return null;
  rodar("narrar.py", arq, saida);
  const falasArq = join(saida, "narracao", "falas.json");
  const legArq = join(saida, "legendas.json");
  if (!existsSync(legArq) || statSync(legArq).mtimeMs < statSync(falasArq).mtimeMs) rodar("legendas.py", "motion", arq, saida);
  return { falas: JSON.parse(readFileSync(falasArq, "utf8")), legendas: JSON.parse(readFileSync(legArq, "utf8")) };
}

async function main() {
  const [arq, saida, ...flags] = process.argv.slice(2);
  if (!arq || !saida) { console.error("uso: node montar.mjs roteiro.json SAIDA [--so-html] [--revisao] [--sem-voz]"); process.exit(2); }
  const roteiro = JSON.parse(readFileSync(arq, "utf8"));
  const formatos = roteiro.formato === "ambos" ? ["vertical", "horizontal"] : [roteiro.formato || "vertical"];
  const env = flags.includes("--so-html") ? process.env : { ...process.env, PATH: pathComFfmpeg() };
  const voz = prepararVoz(arq, resolve(saida), flags);
  let falhou = false;

  for (const formato of formatos) {
    const pasta = resolve(saida, formato);
    const projeto = join(pasta, "projeto");
    const imagens = preparar(projeto, roteiro, dirname(resolve(arq)));
    if (voz?.video) cpSync(voz.video, join(projeto, "assets", "gravacao.mp4"));
    if (voz?.pessoa) cpSync(voz.pessoa, join(projeto, "assets", "pessoa.webm"));
    voz?.falas?.filter((f) => f.wav).forEach((f) => cpSync(join(saida, "narracao", f.wav), join(projeto, "assets", `voz-${f.i}.wav`)));
    const { html, cenas, total } = gerarHtml(roteiro, formato, imagens, voz);
    writeFileSync(join(projeto, "index.html"), html);
    writeFileSync(join(pasta, "cenas.json"), JSON.stringify(cenas.map(({ i, tipo, t0, fim, minimo, fala, em }) => ({ i, tipo, t0, fim, minimo, fala, em })), null, 2));
    cenas.filter((c) => c.duracao && c.duracao < c.minimo).forEach((c) =>
      console.warn(`aviso: cena ${c.i + 1} pediu ${c.duracao} s, mas a leitura exige ${c.minimo} s (usei ${c.minimo}).`));
    cenas.avisos.forEach((a) => console.warn("aviso: " + a));

    const erros = lint(html);
    if (erros.length) {
      console.error(`lint-cena: ${erros.length} problema(s) em ${formato}`);
      erros.forEach((e) => console.error("  ✗ " + e));
      falhou = true;
      continue;
    }
    console.log(`${formato}: ${cenas.length} cenas, ${total.toFixed(1)} s, lint ok`);

    // Gates de antes do render (Fase 6): bloqueiam, a menos que --forcar.
    const [w, h] = DIM[formato];
    const antes = [...await checkLegibilidade(projeto, cenas, { largura: w, altura: h, sobre: Boolean(roteiro.gravacao) }),
      ...checkLegendas(roteiro, voz), ...checkLeitura(cenas)];
    console.log(relatorio("gates (antes do render)", antes));
    writeFileSync(join(pasta, "gates.json"), JSON.stringify({ antes }, null, 2));
    if (antes.length && !flags.includes("--forcar")) { falhou = true; continue; }
    if (flags.includes("--so-html")) continue;

    if (flags.includes("--revisao")) {
      const tempos = cenas.map((c) => Math.max(c.t0, c.fim - 0.5).toFixed(2)).join(",");
      hyperframes(["snapshot", "--at", tempos, "--no-end", "-o", join(pasta, "revisao")], projeto, env);
    }
    const nome = (roteiro.titulo || "Gaspar Vídeo").replace(/[<>:"/\\|?*\u0000-\u001f]/g, " -").replace(/\s+/g, " ").trim();
    const mp4 = resolve(saida, `${nome} (${formato}).mp4`);
    const bruto = join(pasta, "bruto.mp4");
    hyperframes(["render", "-o", bruto, "-f", String(FPS), "-q", "delivery"], projeto, env);
    // Pós (Fase 3): SFX nos marcadores, trilha com ducking, −14 LUFS, LUT de marca.
    process.env.PATH = env.PATH;
    const trilha = flags.includes("--sem-trilha") || roteiro.trilha === false ? null
      : roteiro.trilha ? resolve(dirname(resolve(arq)), roteiro.trilha) : trilhaPadrao();
    const r = await posProduzir({ bruto, projeto, final: mp4, trilha, sfx: !flags.includes("--sem-sfx"),
      lut: !flags.includes("--sem-lut") && roteiro.lut !== false });
    const lu = medirLoudness(mp4);
    console.log(`→ ${mp4}
  ${r.sfx} SFX, trilha ${trilha ? "com ducking" : "não"}, ${lu.I} LUFS, pico ${lu.TP} dBTP`);
    const depois = [...checkDuracao(mp4), ...checkAudio(mp4)];
    console.log(relatorio("gates (depois do render)", depois));
    const quadros = previa(mp4, pasta);
    console.log(`  prévia para o diário: ${quadros.join(", ")}`);
    writeFileSync(join(pasta, "gates.json"), JSON.stringify({ antes, depois, previa: quadros }, null, 2));
    if (depois.length) falhou = true;
  }
  process.exit(falhou ? 1 : 0);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
