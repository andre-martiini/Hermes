// Pós-produção no FFmpeg: SFX nos marcadores do kit, trilha com ducking sob a voz, loudness −14 LUFS e LUT.
//
//   Chamado pelo montar.mjs depois do render (flags --sem-trilha, --sem-sfx, --sem-lut; "trilha" no roteiro).
//
// O áudio do bruto é a "voz" (narração do motion ou som original da gravação na sobreposição).
// O pico de cada SFX cai no pico da curva (marcador do kit.js), não no início do arquivo.
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, renameSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const SKILL = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SFX_MAP = JSON.parse(readFileSync(join(SKILL, "kit", "sfx-map.json"), "utf8"));
const NIVEL = { sfx: -12, trilha: -9 }; // dB: SFX em relação à voz; trilha antes do ducking
// TP mira em −2,0: o gate exige ≤ −1,5 e o loudnorm erra alguns décimos em gravação real com picos fortes.
const ALVO = { I: -14, TP: -2.0, LRA: 11 };
// Limitador de true-peak: a 4× a taxa (pega o pico entre amostras), teto −3 dBFS; −2,3 dBTP no AAC no pior caso testado.
export const LIMITADOR = "aresample=192000,alimiter=limit=0.708:level=disabled:attack=1:release=60";

const ff = (args, opts = {}) => execFileSync("ffmpeg", ["-hide_banner", "-y", ...args], { maxBuffer: 1 << 28, ...opts });

// Abre o index.html do projeto no Chrome do HyperFrames e roda `fn(pagina)` (marcadores, checagens).
export async function comPagina(projeto, fn, { largura, altura } = {}) {
  const { default: puppeteer } = await import("puppeteer-core");
  const nav = await puppeteer.launch({ executablePath: chromeDoHyperframes(), args: ["--allow-file-access-from-files"] });
  try {
    const pg = await nav.newPage();
    if (largura) await pg.setViewport({ width: largura, height: altura });
    await pg.goto(pathToFileURL(join(projeto, "index.html")).href, { waitUntil: "load" });
    await pg.waitForFunction("Array.isArray(window.__sfx) && document.fonts.status === 'loaded'", { timeout: 15000 });
    return await fn(pg);
  } finally {
    await nav.close();
  }
}

let _chrome;
// HYPERFRAMES_BROWSER_PATH (ou PRODUCER_HEADLESS_SHELL_PATH) aponta um Chrome já instalado: é o caminho em
// máquina/nuvem sem acesso ao download do chrome-headless-shell (ex.: /usr/bin/google-chrome).
function chromeDoHyperframes() {
  if (_chrome) return _chrome;
  const env = process.env.HYPERFRAMES_BROWSER_PATH || process.env.PRODUCER_HEADLESS_SHELL_PATH;
  if (env && existsSync(env)) return (_chrome = env);
  const bin = join(SKILL, "node_modules", "hyperframes", "bin", "hyperframes.mjs");
  const saida = execFileSync(process.execPath, [bin, "browser", "ensure"], { stdio: ["ignore", "pipe", "pipe"] }).toString().trim();
  const caminho = saida.match(/Path:\s*(.+)/)?.[1].trim();
  _chrome = caminho && existsSync(caminho) ? caminho : undefined;
  if (!_chrome) throw new Error(`Chrome do HyperFrames não encontrado ("hyperframes browser ensure" disse: ${saida.slice(-200)}). ` +
    "Rode: node node_modules/hyperframes/bin/hyperframes.mjs browser ensure");
  return _chrome;
}

// Marcadores {t, evento} que o kit.js deixou em window.__sfx.
export const marcadores = (projeto) => comPagina(projeto, (pg) => pg.evaluate("window.__sfx"));

// Onde fica o pico (s) dentro de cada arquivo de SFX.
function picoDoSom(arq) {
  const pcm = ff(["-loglevel", "error", "-i", arq, "-f", "f32le", "-ac", "1", "-ar", "8000", "-"]);
  const a = new Float32Array(pcm.buffer, pcm.byteOffset, pcm.length / 4);
  let k = 0;
  for (let i = 1; i < a.length; i++) if (Math.abs(a[i]) > Math.abs(a[k])) k = i;
  return k / 8000;
}

const temAudio = (arq) => execFileSync("ffprobe", ["-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", arq])
  .toString().trim() !== "";
const duracao = (arq) => +execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq]).toString().trim();

export function trilhaPadrao() {
  const raiz = join(homedir(), ".claude", "skills");
  const achar = (d) => {
    for (const e of existsSync(d) ? readdirSync(d, { withFileTypes: true }) : []) {
      const p = join(d, e.name);
      if (e.isDirectory()) { const r = achar(p); if (r) return r; }
      else if (p.endsWith(join("tutorial-sistema", "assets", "trilha.m4a"))) return p;
    }
    return null;
  };
  return achar(raiz);
}

// Ambiente (cafeteria, rua…): loop já normalizado a −14 LUFS (ambiente.py); entra `nivel_db` abaixo da voz,
// sem graves (passa-alta 120 Hz) nem agudos de sobra (passa-baixa 8 kHz) para não disputar com a fala,
// com fade e um ducking leve pela voz. Referência: voz 0, SFX −12, trilha −9 (com ducking), ambiente −24 a −28.
export const AMBIENTE_PADRAO = { nivel_db: -26, fade: 1.0 };

export function filtroAudio({ voz, trilha, ambientes = [], sfx, total }) {
  // Entradas: 0 = bruto, 1 = trilha (se houver), depois um loop por ambiente, depois um arquivo por SFX distinto.
  const partes = [];
  const mix = [];
  let n = trilha ? 2 : 1;
  const chaves = voz ? (trilha ? 1 : 0) + ambientes.length : 0;
  if (voz) partes.push(`[0:a]aresample=48000,asplit=${1 + Math.max(1, chaves)}[voz]${Array.from({ length: Math.max(1, chaves) }, (_, k) => `[chave${k}]`).join("")}`), mix.push("[voz]");
  let k = 0;
  if (trilha) {
    partes.push(`[1:a]aresample=48000,volume=${NIVEL.trilha}dB,atrim=0:${total},afade=t=out:st=${Math.max(0, total - 1.5)}:d=1.5[tr0]`);
    // Ducking: a voz comprime a trilha (~9 dB a menos enquanto há fala; ratio 3 dá ~10, 8 dá ~13).
    if (voz) partes.push(`[tr0][chave${k++}]sidechaincompress=threshold=0.02:ratio=2.5:attack=15:release=350:makeup=1[tr]`);
    else partes.push(`[tr0]anull[tr]`);
    mix.push("[tr]");
  }
  ambientes.forEach((a, j) => {
    const idx = n++, ini = Math.max(0, a.inicio || 0), fim = Math.min(total, a.fim ?? total), dur = Math.max(0.1, fim - ini);
    const fade = Math.min(a.fade ?? AMBIENTE_PADRAO.fade, dur / 2);
    partes.push(`[${idx}:a]aresample=48000,highpass=f=120,lowpass=f=8000,volume=${a.nivel_db ?? AMBIENTE_PADRAO.nivel_db}dB,` +
      `atrim=0:${dur.toFixed(3)},afade=t=in:d=${fade}:curve=qsin,afade=t=out:st=${(dur - fade).toFixed(3)}:d=${fade}:curve=qsin,` +
      `adelay=${Math.round(ini * 1000)}:all=1[am${j}]`);
    if (voz) partes.push(`[am${j}][chave${k++}]sidechaincompress=threshold=0.03:ratio=1.8:attack=30:release=500:makeup=1[amb${j}]`);
    else partes.push(`[am${j}]anull[amb${j}]`);
    mix.push(`[amb${j}]`);
  });
  if (voz && !chaves) partes.push(`[chave0]anullsink`);
  const porArquivo = new Map();
  sfx.forEach((s) => { if (!porArquivo.has(s.arq)) porArquivo.set(s.arq, []); porArquivo.get(s.arq).push(s); });
  for (const usos of porArquivo.values()) {
    const idx = n++;
    const rotulos = usos.map((_, k) => `[s${idx}_${k}]`);
    partes.push(`[${idx}:a]aresample=48000,volume=${NIVEL.sfx}dB,asplit=${usos.length}${rotulos.join("")}`);
    usos.forEach((u, k) => {
      const ms = Math.max(0, Math.round((u.t - u.pico) * 1000));
      partes.push(`${rotulos[k]}adelay=${ms}:all=1[d${idx}_${k}]`);
      mix.push(`[d${idx}_${k}]`);
    });
  }
  if (!mix.length) partes.push(`anullsrc=r=48000:cl=stereo,atrim=0:${total}[mix]`);
  else partes.push(`${mix.join("")}amix=inputs=${mix.length}:normalize=0:duration=longest,apad,atrim=0:${total}[mix]`);
  return { filtro: partes.join(";"), arquivosSfx: [...porArquivo.keys()] };
}

export async function posProduzir({ bruto, projeto, final, trilha = trilhaPadrao(), ambientes = [], sfx = true, lut = true }) {
  const total = duracao(bruto);
  const voz = temAudio(bruto);
  const eventos = sfx ? (await marcadores(projeto)) : [];
  const picos = new Map();
  const usos = eventos.filter((e) => SFX_MAP[e.evento]).map((e) => {
    const arq = join(SKILL, "assets", "sfx", `${SFX_MAP[e.evento]}.mp3`);
    if (!picos.has(arq)) picos.set(arq, picoDoSom(arq));
    return { t: e.t, arq, pico: picos.get(arq) };
  }).filter((u) => u.t < total);
  const { filtro, arquivosSfx } = filtroAudio({ voz, trilha, ambientes, sfx: usos, total });
  const entradas = ["-i", bruto, ...(trilha ? ["-stream_loop", "-1", "-i", trilha] : []),
    ...ambientes.flatMap((a) => ["-stream_loop", "-1", "-i", a.arquivo]), ...arquivosSfx.flatMap((a) => ["-i", a])];

  // Loudness em dois passes: mede, depois corrige linear para −14 LUFS. O loudnorm linear não garante o teto
  // quando a voz tem picos: o LIMITADOR depois dele segura o true-peak (o gate mede no AAC final).
  const m = medirParaNormalizar(entradas, filtro);
  const norm = `loudnorm=I=${ALVO.I}:TP=${ALVO.TP}:LRA=${ALVO.LRA}:measured_I=${m.input_i}:measured_TP=${m.input_tp}` +
    `:measured_LRA=${m.input_lra}:measured_thresh=${m.input_thresh}:offset=${m.target_offset}:linear=true`;
  const lutArq = join(SKILL, "assets", "lut", "gaspar.cube");
  const video = lut ? ["-vf", "lut3d=gaspar.cube"] : [];
  ff(["-loglevel", "error", ...entradas,
    "-filter_complex", `${filtro};[mix]${norm},${LIMITADOR},aresample=48000[a]`, "-map", "0:v", "-map", "[a]",
    ...video, "-c:v", lut ? "libx264" : "copy", ...(lut ? ["-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"] : []),
    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", String(total), resolve(final)], { cwd: dirname(lutArq) });
  // O limitador tira volume quando a voz tem muitos picos (dublagem: −15,1 LUFS no teste de 01/11/2026).
  // Mede o arquivo final e, se saiu do alvo, corrige com ganho fixo + limitador de novo (só o áudio).
  const lu = medirLoudness(resolve(final));
  if (Math.abs(lu.I - ALVO.I) > 0.4) {
    const tmp = resolve(final) + ".aj.mp4";
    ff(["-loglevel", "error", "-i", resolve(final), "-map", "0:v", "-map", "0:a", "-c:v", "copy",
      "-af", `volume=${(ALVO.I - lu.I).toFixed(2)}dB,${LIMITADOR},aresample=48000`, "-c:a", "aac", "-b:a", "192k",
      "-movflags", "+faststart", tmp]);
    renameSync(tmp, resolve(final));
  }
  return { total, voz, sfx: usos.length };
}

// ffmpeg escreve as medições no stderr.
function stderrDe(args) {
  const r = spawnSync("ffmpeg", ["-hide_banner", "-nostats", ...args], { maxBuffer: 1 << 28 });
  if (r.status !== 0) throw new Error("ffmpeg falhou: " + r.stderr.toString().slice(-600));
  return r.stderr.toString();
}

function medirParaNormalizar(entradas, filtro) {
  const err = stderrDe([...entradas, "-filter_complex",
    `${filtro};[mix]loudnorm=I=${ALVO.I}:TP=${ALVO.TP}:LRA=${ALVO.LRA}:print_format=json[o]`, "-map", "[o]", "-f", "null", "-"]);
  return JSON.parse(err.slice(err.lastIndexOf("{"), err.lastIndexOf("}") + 1));
}

// Mede o resultado (EBU R128): {I, TP} em LUFS / dBTP.
export function medirLoudness(arq) {
  const err = stderrDe(["-i", arq, "-af", "ebur128=peak=true", "-f", "null", "-"]);
  const resumo = err.slice(err.lastIndexOf("Summary:"));
  return { I: +resumo.match(/I:\s+(-?[\d.]+) LUFS/)[1], TP: +resumo.match(/Peak:\s+(-?[\d.]+) dBFS/)[1] };
}
