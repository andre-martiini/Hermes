// Pós-produção no FFmpeg: SFX nos marcadores do kit, trilha com ducking sob a voz, loudness −14 LUFS e LUT.
//
//   Chamado pelo montar.mjs depois do render (flags --sem-trilha, --sem-sfx, --sem-lut; "trilha" no roteiro).
//
// O áudio do bruto é a "voz" (narração do motion ou som original da gravação na sobreposição).
// O pico de cada SFX cai no pico da curva (marcador do kit.js), não no início do arquivo.
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const SKILL = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SFX_MAP = JSON.parse(readFileSync(join(SKILL, "kit", "sfx-map.json"), "utf8"));
const NIVEL = { sfx: -12, trilha: -9 }; // dB: SFX em relação à voz; trilha antes do ducking
const ALVO = { I: -14, TP: -1.5, LRA: 11 };

const ff = (args, opts = {}) => execFileSync("ffmpeg", ["-hide_banner", "-y", ...args], { maxBuffer: 1 << 28, ...opts });

// Marcadores {t, evento}: abre a página no Chrome do HyperFrames e lê window.__sfx.
export async function marcadores(projeto) {
  const { default: puppeteer } = await import("puppeteer-core");
  const base = join(homedir(), ".cache", "hyperframes", "chrome", "chrome-headless-shell");
  const versao = readdirSync(base).sort().at(-1);
  const exe = join(base, versao, "chrome-headless-shell-win64", "chrome-headless-shell.exe");
  const nav = await puppeteer.launch({ executablePath: existsSync(exe) ? exe : undefined, args: ["--allow-file-access-from-files"] });
  try {
    const pg = await nav.newPage();
    await pg.goto(pathToFileURL(join(projeto, "index.html")).href, { waitUntil: "load" });
    await pg.waitForFunction("Array.isArray(window.__sfx)", { timeout: 15000 });
    return await pg.evaluate("window.__sfx");
  } finally {
    await nav.close();
  }
}

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

export function filtroAudio({ voz, trilha, sfx, total }) {
  // Entradas: 0 = bruto, 1 = trilha (se houver), depois um arquivo por SFX distinto.
  const partes = [];
  const mix = [];
  let n = trilha ? 2 : 1;
  if (voz) partes.push(`[0:a]aresample=48000,asplit=2[voz][chave]`), mix.push("[voz]");
  if (trilha) {
    partes.push(`[1:a]aresample=48000,volume=${NIVEL.trilha}dB,atrim=0:${total},afade=t=out:st=${Math.max(0, total - 1.5)}:d=1.5[tr0]`);
    // Ducking: a voz comprime a trilha (~9 dB a menos enquanto há fala; ratio 3 dá ~10, 8 dá ~13).
    if (voz) partes.push(`[tr0][chave]sidechaincompress=threshold=0.02:ratio=2.5:attack=15:release=350:makeup=1[tr]`);
    else partes.push(`[tr0]anull[tr]`);
    mix.push("[tr]");
  } else if (voz) partes.push(`[chave]anullsink`);
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
  partes.push(`${mix.join("")}amix=inputs=${mix.length}:normalize=0:duration=longest,apad,atrim=0:${total}[mix]`);
  return { filtro: partes.join(";"), arquivosSfx: [...porArquivo.keys()] };
}

export async function posProduzir({ bruto, projeto, final, trilha = trilhaPadrao(), sfx = true, lut = true }) {
  const total = duracao(bruto);
  const voz = temAudio(bruto);
  const eventos = sfx ? (await marcadores(projeto)) : [];
  const picos = new Map();
  const usos = eventos.filter((e) => SFX_MAP[e.evento]).map((e) => {
    const arq = join(SKILL, "assets", "sfx", `${SFX_MAP[e.evento]}.mp3`);
    if (!picos.has(arq)) picos.set(arq, picoDoSom(arq));
    return { t: e.t, arq, pico: picos.get(arq) };
  }).filter((u) => u.t < total);
  const { filtro, arquivosSfx } = filtroAudio({ voz, trilha, sfx: usos, total });
  const entradas = ["-i", bruto, ...(trilha ? ["-stream_loop", "-1", "-i", trilha] : []), ...arquivosSfx.flatMap((a) => ["-i", a])];

  // Loudness em dois passes: mede, depois corrige linear para −14 LUFS / −1,5 dBTP.
  const m = medirParaNormalizar(entradas, filtro);
  const norm = `loudnorm=I=${ALVO.I}:TP=${ALVO.TP}:LRA=${ALVO.LRA}:measured_I=${m.input_i}:measured_TP=${m.input_tp}` +
    `:measured_LRA=${m.input_lra}:measured_thresh=${m.input_thresh}:offset=${m.target_offset}:linear=true`;
  const lutArq = join(SKILL, "assets", "lut", "gaspar.cube");
  const video = lut ? ["-vf", "lut3d=gaspar.cube"] : [];
  ff(["-loglevel", "error", ...entradas,
    "-filter_complex", `${filtro};[mix]${norm},aresample=48000[a]`, "-map", "0:v", "-map", "[a]",
    ...video, "-c:v", lut ? "libx264" : "copy", ...(lut ? ["-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"] : []),
    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", String(total), resolve(final)], { cwd: dirname(lutArq) });
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
