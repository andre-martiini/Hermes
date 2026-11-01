// Quality gates (Fase 6): nenhum vídeo sai sem passar. Cada falha diz a regra, a cena e o texto.
//   antes do render: lint-cena (montar), check-legibilidade, check-legendas  → bloqueiam o render
//   depois do render: check-duracao, check-audio                           → falham o montar (exit 1)
// Prévia: quadros em 10%, 50% e 90% para o diário da ação.
import { execFileSync, spawnSync } from "node:child_process";
import { join } from "node:path";
import { comPagina, medirLoudness } from "./pos.mjs";

export const REGRAS = {
  safeArea: { topo: 0.15, base: 0.2 }, // 9:16
  fonteMinPx: 48, // em 1080×1920
  contrasteMin: 4.5,
  loudness: { I: -14, tolI: 1, TPmax: -1.5 },
  silencioMaxS: 1.5,
  difDuracaoS: 0.1,
  confiancaMin: 0.6,
};

const falha = (regra, detalhe, extra = {}) => ({ regra, detalhe, ...extra });

// Roda no navegador: mede cada texto visível com a cena assentada.
function medirNaPagina({ instantes, sobre, regras }) {
  const tl = window.__timelines.main;
  const W = innerWidth, H = innerHeight, vertical = H > W;
  const lum = (c) => {
    const [r, g, b] = c.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const rgba = (s) => (s.match(/[\d.]+/g) || []).map(Number);
  const fundo = (el) => {
    for (let e = el; e; e = e.parentElement) {
      const c = rgba(getComputedStyle(e).backgroundColor);
      if (c.length >= 3 && (c[3] ?? 1) > 0.5) return c;
    }
    return sobre ? null : rgba(getComputedStyle(document.body).backgroundColor);
  };
  const visivel = (el) => {
    for (let e = el; e; e = e.parentElement) if (+getComputedStyle(e).opacity === 0 || getComputedStyle(e).visibility === "hidden") return false;
    return true;
  };
  const textos = (raiz) => [...raiz.querySelectorAll("*")].filter((e) =>
    [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()));
  const achados = [];
  const checar = (el, onde) => {
    if (!visivel(el)) return;
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    const texto = el.textContent.trim().slice(0, 40);
    if (vertical && (r.top < regras.safeArea.topo * H - 1 || r.bottom > (1 - regras.safeArea.base) * H + 1))
      achados.push({ regra: "safe-area-9x16", detalhe: `texto de ${Math.round(r.top)} a ${Math.round(r.bottom)} px; permitido de ${Math.round(regras.safeArea.topo * H)} a ${Math.round((1 - regras.safeArea.base) * H)} px`, onde, texto });
    if (vertical && parseFloat(st.fontSize) < regras.fonteMinPx - 0.5)
      achados.push({ regra: "fonte-minima", detalhe: `${parseFloat(st.fontSize).toFixed(0)} px < ${regras.fonteMinPx} px`, onde, texto });
    const bg = fundo(el);
    if (bg) {
      const [a, b] = [lum(rgba(st.color)), lum(bg)].sort((x, y) => y - x);
      const c = (a + 0.05) / (b + 0.05);
      if (c < regras.contrasteMin) achados.push({ regra: "contraste", detalhe: `${c.toFixed(2)}:1 < ${regras.contrasteMin}:1`, onde, texto });
    }
  };
  instantes.forEach(({ i, t }) => {
    tl.seek(t, false);
    textos(document.getElementById(`cena-${i}`)).forEach((el) => checar(el, `cena ${i + 1}`));
  });
  document.querySelectorAll(".legenda").forEach((leg, n) => {
    tl.seek(+leg.dataset.start + 0.05, false);
    const r = leg.getBoundingClientRect();
    if (vertical && (r.top < regras.safeArea.topo * H || r.bottom > (1 - regras.safeArea.base) * H + 1))
      achados.push({ regra: "safe-area-9x16", detalhe: `legenda de ${Math.round(r.top)} a ${Math.round(r.bottom)} px`, onde: `legenda ${n + 1}`, texto: leg.textContent.trim().slice(0, 40) });
    if (vertical && parseFloat(getComputedStyle(leg).fontSize) < regras.fonteMinPx - 0.5)
      achados.push({ regra: "fonte-minima", detalhe: `legenda com ${parseFloat(getComputedStyle(leg).fontSize)} px`, onde: `legenda ${n + 1}`, texto: "" });
  });
  return achados;
}

export async function checkLegibilidade(projeto, cenas, { largura, altura, sobre = false }) {
  const instantes = cenas.map((c) => ({ i: c.i, t: Math.max(c.t0, c.fim - 0.4) }));
  return comPagina(projeto, (pg) => pg.evaluate(medirNaPagina, { instantes, sobre, regras: REGRAS }), { largura, altura });
}

// Motion: a legenda de cada cena é a narração, palavra por palavra. Sobreposição: palavra incerta só passa revisada.
export function checkLegendas(roteiro, voz) {
  if (!voz) return [];
  if (roteiro.gravacao) {
    const baixas = voz.legendas.filter((c) => c.confidence < REGRAS.confiancaMin && !c.revisado);
    return roteiro.legendas_revisadas || !baixas.length ? [] : [falha("legenda-nao-revisada",
      `${baixas.length} palavra(s) com confiança < ${REGRAS.confiancaMin}: ${baixas.map((c) => c.text.trim()).join(", ")}. ` +
      `Corrija em legendas.json (marque "revisado": true) ou ponha "legendas_revisadas": true no roteiro.`)];
  }
  return roteiro.cenas.flatMap((c, i) => {
    if (!c.narracao) return [];
    const leg = (voz.legendas[i] || []).map((t) => t.text).join("");
    return leg === c.narracao.trim().split(/\s+/).join(" ") ? [] : [falha("legenda-cobertura", `cena ${i + 1}: a legenda não reproduz a narração`, { esperado: c.narracao, obtido: leg })];
  });
}

const probe = (arq, sel) => +execFileSync("ffprobe", ["-v", "error", "-select_streams", sel, "-show_entries", "stream=duration",
  "-of", "csv=p=0", arq]).toString().trim();

export function checkDuracao(mp4, cenas) {
  const erros = [];
  const v = probe(mp4, "v:0"), a = probe(mp4, "a:0");
  if (Math.abs(v - a) > REGRAS.difDuracaoS) erros.push(falha("duracao-audio", `vídeo ${v.toFixed(2)} s × áudio ${a.toFixed(2)} s`));
  cenas.filter((c) => c.fim - c.t0 < c.minimo - 0.01).forEach((c) =>
    erros.push(falha("tempo-de-leitura", `cena ${c.i + 1}: ${(c.fim - c.t0).toFixed(2)} s < ${c.minimo} s`)));
  return erros;
}

export function checkAudio(mp4) {
  const erros = [];
  const { I, TP } = medirLoudness(mp4);
  if (Math.abs(I - REGRAS.loudness.I) > REGRAS.loudness.tolI) erros.push(falha("loudness", `${I} LUFS (alvo −14 ± 1)`));
  if (TP > REGRAS.loudness.TPmax + 0.05) erros.push(falha("true-peak", `${TP} dBTP > ${REGRAS.loudness.TPmax}`));
  const r = spawnSync("ffmpeg", ["-hide_banner", "-nostats", "-i", mp4, "-af", `silencedetect=noise=-50dB:d=${REGRAS.silencioMaxS}`, "-f", "null", "-"]);
  const total = probe(mp4, "a:0");
  for (const m of r.stderr.toString().matchAll(/silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+)/g)) {
    const [ini, fim] = [+m[1], +m[2]];
    if (ini > 0.5 && fim < total - 0.5) erros.push(falha("silencio", `${(fim - ini).toFixed(1)} s de silêncio aos ${ini.toFixed(1)} s`));
  }
  return erros;
}

// Quadros em 10%, 50% e 90% (PNG) para o André ver antes da entrega.
export function previa(mp4, pasta) {
  const total = probe(mp4, "v:0");
  return [0.1, 0.5, 0.9].map((f) => {
    const png = join(pasta, `previa-${Math.round(f * 100)}.png`);
    execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-ss", (total * f).toFixed(2), "-i", mp4, "-frames:v", "1", png]);
    return png;
  });
}

export function relatorio(etapa, erros) {
  if (!erros.length) return `${etapa}: ok`;
  return `${etapa}: ${erros.length} falha(s)\n` + erros.map((e) =>
    `  ✗ [${e.regra}] ${e.onde ? e.onde + ": " : ""}${e.detalhe}${e.texto ? ` — "${e.texto}"` : ""}`).join("\n");
}
