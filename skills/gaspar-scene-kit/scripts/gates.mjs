// Quality gates (Fase 6): nenhum vídeo sai sem passar. Cada falha diz a regra, a cena e o texto.
//   antes do render: lint-cena (montar), check-legibilidade, check-legendas, check-composicao (título cortado,
//                    título oculto pela pessoa, cartão sobre o rosto; escolhe o modo do título) → bloqueiam
//   depois do render: check-duracao, check-audio, check-quadros (rosto e corte nos quadros reais) → exit 1
// Prévia: quadros em 10%, 50% e 90% para o diário da ação.
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { comPagina, medirLoudness } from "./pos.mjs";

export const REGRAS = {
  // 9:16. O título "atrás da pessoa" pode subir até 5%: ele precisa ficar acima da cabeça.
  safeArea: { topo: 0.15, base: 0.2, topoTituloAtras: 0.05 },
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
    // Caixa do texto de verdade (Range): um texto que transborda o bloco pode sair da tela sem o bloco sair.
    const rg = document.createRange(); rg.selectNodeContents(el);
    const rt = rg.getBoundingClientRect();
    if (rt.width && (rt.left < -1 || rt.top < -1 || rt.right > W + 1 || rt.bottom > H + 1))
      achados.push({ regra: "titulo-cortado", detalhe: `texto de x ${Math.round(rt.left)}–${Math.round(rt.right)}, y ${Math.round(rt.top)}–${Math.round(rt.bottom)} fora de 0–${W} × 0–${H}`, onde, texto });
    const topo = el.closest(".atras") ? regras.safeArea.topoTituloAtras : regras.safeArea.topo;
    if (vertical && (r.top < topo * H - 1 || r.bottom > (1 - regras.safeArea.base) * H + 1))
      achados.push({ regra: "safe-area-9x16", detalhe: `texto de ${Math.round(r.top)} a ${Math.round(r.bottom)} px; permitido de ${Math.round(topo * H)} a ${Math.round((1 - regras.safeArea.base) * H)} px`, onde, texto });
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

// Antes do render: nenhuma cena abaixo do tempo de leitura (na sobreposição, o fim da gravação pode cortá-la).
export const checkLeitura = (cenas) => cenas.filter((c) => c.fim - c.t0 < c.minimo - 0.01).map((c) =>
  falha("tempo-de-leitura", `cena ${c.i + 1}: ${(c.fim - c.t0).toFixed(2)} s < ${c.minimo} s (comece antes ou encurte o texto)`));

export function checkDuracao(mp4) {
  const v = probe(mp4, "v:0"), a = probe(mp4, "a:0");
  return Math.abs(v - a) > REGRAS.difDuracaoS ? [falha("duracao-audio", `vídeo ${v.toFixed(2)} s × áudio ${a.toFixed(2)} s`)] : [];
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

// ---------------------------------------------------------------- composição × pessoa (título, rosto, recorte)
// A máscara da pessoa (alfa do pessoa.webm, 10 quadros/s, grade de 10 px) e o rosto do MediaPipe (rastro.json do
// efeitos.py) dizem onde ela está a cada instante. Os gates abaixo comparam isso com as caixas reais do texto.
const GW = 108, GH = 192, PASSO = 10, FPS_MASCARA = 10;
export const MODOS_TITULO = ["atras", "abaixo", "antes", "topo"];
export const DUR_ANTES = 1.2;
const VISIVEL_MIN = 0.7; // cada letra do título "atrás" precisa de ≥ 70% visível (p90 no tempo)

export function analisarPessoa(webm, rastroArq) {
  const bruto = execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-c:v", "libvpx-vp9", "-i", webm, "-vf",
    `fps=${FPS_MASCARA},alphaextract,scale=${GW}:${GH}`, "-f", "rawvideo", "-pix_fmt", "gray", "-"], { maxBuffer: 1 << 28 });
  // Sem rastro (cache antigo, recorte de outro pipeline), os gates de rosto passariam calados: falha alto.
  const rastro = existsSync(rastroArq) ? JSON.parse(readFileSync(rastroArq, "utf8")) : [];
  const nMascara = Math.floor(bruto.length / (GW * GH));
  if (rastro.length < (nMascara / FPS_MASCARA) * 30 * 0.9)
    throw new Error(`${rastroArq} ausente ou incompleto (${rastro.length} quadros): apague ${webm} para refazer o recorte com o rastreio do rosto.`);
  const quadros = [];
  let ultimo = null; // quadro sem rosto detectado (perfil, mão na frente): vale o último rosto conhecido
  for (let k = 0; (k + 1) * GW * GH <= bruto.length; k++) {
    const alfa = bruto.subarray(k * GW * GH, (k + 1) * GW * GH);
    let topo = null;
    for (let y = 0; y < GH && topo == null; y++) {
      let n = 0;
      for (let x = 0; x < GW; x++) n += alfa[y * GW + x] > 128;
      if (n >= 3) topo = y * PASSO;
    }
    const pts = rastro[Math.round((k / FPS_MASCARA) * 30)]?.rosto || ultimo;
    if (pts) ultimo = pts;
    let rosto = null, cabeca = null;
    if (pts) {
      const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
      rosto = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
      const [x0, y0, x1, y1] = rosto, w = x1 - x0, h = y1 - y0;
      cabeca = [x0 - 0.12 * w, Math.min(topo ?? y0, y0 - 0.45 * h), x1 + 0.12 * w, y1]; // + cabelo
    }
    quadros.push({ t: k / FPS_MASCARA, alfa, topo, rosto, cabeca });
  }
  // O começo sem rosto detectado herda o 1º rosto conhecido.
  const primeiro = quadros.find((q) => q.rosto);
  for (const q of quadros) { if (q.rosto) break; q.rosto = primeiro?.rosto ?? null; q.cabeca = primeiro?.cabeca ?? null; }
  return { quadros, em: (t) => quadros[Math.min(quadros.length - 1, Math.max(0, Math.round(t * FPS_MASCARA)))] };
}

const pct = (v, p) => { const s = [...v].sort((a, b) => a - b); return s.length ? s[Math.floor(p * (s.length - 1))] : 0; };
const cruza = (a, b) => Boolean(a && b && a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3]);

// Fração da caixa coberta pela pessoa (alfa > 0,5) no quadro q.
export function cobertura(q, [x0, y0, x1, y1]) {
  let n = 0, cob = 0;
  for (let y = Math.max(0, Math.floor(y0 / PASSO)); y < Math.min(GH, Math.ceil(y1 / PASSO)); y++)
    for (let x = Math.max(0, Math.floor(x0 / PASSO)); x < Math.min(GW, Math.ceil(x1 / PASSO)); x++) { n++; cob += q.alfa[y * GW + x] > 128; }
  return n ? cob / n : 0;
}

// Topo da cabeça (p10: a posição mais alta que ela alcança) e queixo (p90: a mais baixa) na janela [t0, t1].
export function janelaPessoa(analise, t0, t1) {
  const qs = analise.quadros.filter((q) => q.t >= t0 - 0.05 && q.t <= t1 + 0.05);
  return { topo: pct(qs.map((q) => q.topo).filter((v) => v != null), 0.1),
    queixo: Math.round(pct(qs.map((q) => q.rosto?.[3]).filter((v) => v != null), 0.9)) || null,
    altura: pct(qs.map((q) => q.rosto && q.rosto[3] - (q.topo ?? q.rosto[1])).filter(Boolean), 0.9) };
}

// Roda no navegador: caixas reais (Range) do título de abertura em cada modo e das cenas de cartão.
function medirComposicao({ titulos, cartoes, modos }) {
  const tl = window.__timelines.main;
  const caixa = (r) => [r.left, r.top, r.right, r.bottom].map(Math.round);
  const deTexto = (e) => { const r = document.createRange(); r.selectNodeContents(e); return caixa(r.getBoundingClientRect()); };
  const res = { titulos: {}, cartoes: {} };
  for (const { i, instantes } of titulos) {
    const sec = document.getElementById(`cena-${i}`), antes = sec.dataset.modoTitulo;
    res.titulos[i] = {};
    for (const m of modos) {
      sec.dataset.modoTitulo = m;
      Kit.ajustarTitulo(sec);
      res.titulos[i][m] = instantes.map((t) => {
        tl.seek(t, false);
        const g = sec.querySelector(".gigante"), no = g.firstChild;
        const letras = [...no.textContent].map((_, k) => {
          const r = document.createRange(); r.setStart(no, k); r.setEnd(no, k + 1); return caixa(r.getBoundingClientRect());
        }).filter((b) => b[2] > b[0]);
        return { t, letras, textos: [...sec.querySelectorAll(".etiqueta, .gigante")].map(deTexto),
          painel: caixa(sec.querySelector(".bloco").getBoundingClientRect()), fonte: parseFloat(getComputedStyle(g).fontSize) };
      });
    }
    sec.dataset.modoTitulo = antes;
    Kit.ajustarTitulo(sec);
  }
  for (const { i, t } of cartoes) {
    tl.seek(t, false);
    const sec = document.getElementById(`cena-${i}`);
    res.cartoes[i] = { painel: caixa(sec.getBoundingClientRect()), textos: [...sec.querySelectorAll("*")]
      .filter((e) => [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())).map(deTexto) };
  }
  return res;
}

const amostras = (t0, t1) => { const v = []; for (let t = t0; t <= t1 + 1e-6; t += 0.1) v.push(+t.toFixed(2)); return v; };

// Avalia um modo do título: [] = passa; senão a lista de falhas (regra + detalhe). `.pior` = maior oclusão.
export function avaliarTitulo(modo, med, analise, cena, primeiraFala, W = 1080, H = 1920) {
  const erros = [];
  const usar = modo === "antes" ? med.filter((a) => a.t <= cena.t0 + DUR_ANTES - 0.3) : med;
  const textos = usar.flatMap((a) => a.textos);
  const fora = textos.find(([x0, y0, x1, y1]) => x0 < -1 || y0 < -1 || x1 > W + 1 || y1 > H + 1);
  if (fora) erros.push(falha("titulo-cortado", `texto de x ${fora[0]}–${fora[2]}, y ${fora[1]}–${fora[3]} fora de 0–${W} × 0–${H}`));
  const topo = (modo === "atras" ? REGRAS.safeArea.topoTituloAtras : REGRAS.safeArea.topo) * H, base = (1 - REGRAS.safeArea.base) * H;
  const sa = textos.find(([, y0, , y1]) => y0 < topo - 1 || y1 > base + 1);
  if (sa) erros.push(falha("safe-area-9x16", `texto de ${sa[1]} a ${sa[3]} px; permitido de ${Math.round(topo)} a ${Math.round(base)} px`));
  const fonte = Math.min(...usar.map((a) => a.fonte));
  if (fonte < REGRAS.fonteMinPx - 0.5) erros.push(falha("fonte-minima", `título com ${fonte.toFixed(0)} px < ${REGRAS.fonteMinPx} px`));
  let pior = { oculto: 0, t: usar[0]?.t };
  if (modo === "atras") {
    const n = usar[0]?.letras.length || 0;
    for (let k = 0; k < n; k++) {
      const v = usar.map((a) => cobertura(analise.em(a.t), a.letras[k]));
      const p = pct(v, 0.9);
      if (p > pior.oculto) pior = { oculto: p, t: usar[v.indexOf(Math.max(...v))].t };
    }
    if (pior.oculto > 1 - VISIVEL_MIN) erros.push(falha("titulo-oculto",
      `uma letra fica ${Math.round(pior.oculto * 100)}% atrás da pessoa (p90; o máximo é ${Math.round((1 - VISIVEL_MIN) * 100)}%)`));
  } else if (modo !== "antes") {
    const k = modo === "topo" ? "cabeca" : "rosto";
    const bate = usar.find((a) => cruza(a.painel, analise.em(a.t)[k]));
    if (bate) erros.push(falha("rosto-coberto", `o ${modo === "topo" ? "painel" : "título"} encosta ${k === "cabeca" ? "na cabeça" : "no rosto"} aos ${bate.t.toFixed(1)} s`));
  }
  if (modo === "antes" && primeiraFala != null && primeiraFala < cena.t0 + DUR_ANTES - 0.05)
    erros.push(falha("fala-no-cartao", `a fala começa aos ${primeiraFala.toFixed(2)} s, durante o cartão de abertura (${DUR_ANTES} s)`));
  return Object.assign(erros, { pior });
}

// Escolhe o modo de cada título de abertura (ou valida o "modo" do roteiro) e confere os cartões contra o rosto.
// Devolve { falhas, decisoes: {i: {modo, motivos}} }.
export async function checkComposicao(projeto, cenas, analise, legendas, { largura = 1080, altura = 1920, modos = MODOS_TITULO } = {}) {
  const titulos = cenas.filter((c) => c.tipo === "titulo_atras")
    .map((c) => ({ i: c.i, instantes: amostras(c.t0 + 0.75, Math.max(c.t0 + 0.8, c.fim - 0.35)) }));
  const cartoes = cenas.filter((c) => c.tipo !== "titulo_atras" && c.tipo !== "chamada" && c.layout !== "dividido"
    && !(c.tipo === "print" && c.layout === "cheio" && c.fim - c.t0 <= 8)).map((c) => ({ i: c.i, t: Math.max(c.t0, c.fim - 0.4) }));
  const med = await comPagina(projeto, (pg) => pg.evaluate(medirComposicao, { titulos, cartoes, modos }), { largura, altura });
  const falhas = [], decisoes = {};
  for (const { i } of titulos) {
    const c = cenas.find((x) => x.i === i);
    const fala = legendas?.find((tk) => tk.startMs / 1000 >= c.t0 - 0.05)?.startMs / 1000;
    const notas = {};
    let modo = null;
    for (const m of c.modo ? [c.modo] : modos) {
      const e = avaliarTitulo(m, med.titulos[i][m], analise, c, fala, largura, altura);
      notas[m] = { falhas: e.map((x) => `${x.regra}: ${x.detalhe}`), pior: e.pior };
      if (!e.length) { modo = m; break; }
      if (c.modo) falhas.push(...e.map((x) => ({ ...x, onde: `cena ${i + 1} (modo "${m}" do roteiro)` })));
    }
    if (!modo && !c.modo) {
      const j = janelaPessoa(analise, c.t0, c.fim);
      falhas.push(falha("titulo-sem-modo", `nenhum modo cabe: a cabeça ocupa ${Math.round((j.altura / altura) * 100)}% da altura do ` +
        `quadro (topo ${j.topo} px, queixo ${j.queixo} px). Sugestão: regravar mais afastado, ou ` +
        `uma pausa de ${DUR_ANTES} s antes de falar (modo "antes").`, { onde: `cena ${i + 1}`, texto: c.titulo }));
    }
    decisoes[i] = { modo: modo ?? c.modo ?? null, motivos: notas };
  }
  for (const { i, t } of cartoes) {
    const c = cenas.find((x) => x.i === i), m = med.cartoes[i];
    const fora = m.textos.find(([x0, y0, x1, y1]) => x0 < -1 || y0 < -1 || x1 > largura + 1 || y1 > altura + 1);
    if (fora) falhas.push(falha("titulo-cortado", `texto fora da tela (x ${fora[0]}–${fora[2]})`, { onde: `cena ${i + 1}` }));
    // O painel assentado contra o rosto em toda a janela do cartão (desde o fim da entrada).
    const bate = amostras(Math.min(c.t0 + 0.45, t), c.fim - 0.1).find((s) => cruza(m.painel, analise.em(s).rosto));
    if (bate != null) falhas.push(falha("rosto-coberto", `o cartão cobre o rosto aos ${bate.toFixed(1)} s`, { onde: `cena ${i + 1}` }));
  }
  return { falhas, decisoes };
}

// Depois do render, nos quadros reais (0,5 s, meio e fim de cada cartão): o rosto continua o da gravação
// (correlação no retângulo do rosto) e nenhum texto novo encosta na borda da tela.
function quadroRGB(arq, t, w = 270, h = 480) {
  return execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-ss", t.toFixed(3), "-i", arq, "-frames:v", "1", "-vf",
    `scale=${w}:${h}:force_original_aspect_ratio=increase,crop=${w}:${h}`, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], { maxBuffer: 1 << 24 });
}
// Acento da casa (âmbar): matiz 20–55°, saturado e claro.
const ambar = (p, i) => {
  const r = p[i] / 255, g = p[i + 1] / 255, b = p[i + 2] / 255, mx = Math.max(r, g, b), mn = Math.min(r, g, b);
  if (mx < 0.55 || mx - mn < 0.45 * mx || mx !== r) return false;
  const hue = 60 * ((g - b) / (mx - mn));
  return hue >= 20 && hue <= 55;
};
export function correlacao(a, b, w, [x0, y0, x1, y1]) {
  const va = [], vb = [];
  for (let y = Math.max(0, Math.floor(y0)); y < y1; y++) for (let x = Math.max(0, Math.floor(x0)); x < Math.min(w, x1); x++) {
    const i = (y * w + x) * 3; va.push(a[i] + a[i + 1] + a[i + 2]); vb.push(b[i] + b[i + 1] + b[i + 2]);
  }
  if (!va.length) return 1;
  const m = (v) => v.reduce((s, x) => s + x, 0) / v.length, ma = m(va), mb = m(vb);
  let n = 0, da = 0, db = 0;
  va.forEach((x, k) => { n += (x - ma) * (vb[k] - mb); da += (x - ma) ** 2; db += (vb[k] - mb) ** 2; });
  return da && db ? n / Math.sqrt(da * db) : 1;
}

export function checkQuadros(mp4, gravacao, cenas, analise, decisoes = {}) {
  const erros = [], E = 4; // quadros em 270×480 = 1/4 de 1080×1920
  for (const c of cenas) {
    if (c.tipo === "chamada" || c.layout === "dividido" || (c.tipo === "print" && c.layout === "cheio" && c.fim - c.t0 <= 8)) continue;
    const modo = decisoes[c.i]?.modo;
    for (const t of [c.t0 + 0.5, (c.t0 + c.fim) / 2, c.fim - 0.1]) {
      if (t >= c.fim || (modo === "antes" && t > c.t0 + DUR_ANTES - 0.3)) continue;
      const fin = quadroRGB(mp4, t), ori = quadroRGB(gravacao, t), q = analise.em(t);
      if (modo !== "antes" && q.rosto) {
        const r = correlacao(fin, ori, 270, q.rosto.map((v) => v / E));
        if (r < 0.6) erros.push(falha("rosto-coberto", `no quadro de ${t.toFixed(1)} s o rosto difere da gravação (correlação ${r.toFixed(2)})`, { onde: `cena ${c.i + 1}` }));
      }
      if (c.tipo === "titulo_atras") {
        let borda = 0;
        for (let y = 0; y < 480; y++) for (const x of [0, 1, 268, 269]) { const i = (y * 270 + x) * 3; borda += ambar(fin, i) && !ambar(ori, i); }
        if (borda > 6) erros.push(falha("titulo-cortado", `no quadro de ${t.toFixed(1)} s o título encosta na borda da tela`, { onde: `cena ${c.i + 1}` }));
      }
    }
  }
  return erros;
}
