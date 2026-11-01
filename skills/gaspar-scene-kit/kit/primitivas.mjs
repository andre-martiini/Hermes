// Gaspar scene kit — marcação. Cada tipo de cena do roteiro vira uma primitiva do kit.js.
// Aqui só sai HTML com as classes do tokens.css; o movimento é todo do kit.js.

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

const cab = (c) =>
  (c.etiqueta ? `<div class="etiqueta cab">${esc(c.etiqueta)}</div>` : "") +
  (c.titulo ? `<div class="titulo cab">${esc(c.titulo)}</div>` : "");

const numeroFinal = (c) => (c.prefixo || "") +
  new Intl.NumberFormat("pt-BR", { minimumFractionDigits: c.casas || 0, maximumFractionDigits: c.casas || 0 }).format(c.valor) + (c.sufixo || "");

const palavras = (...textos) => textos.flat().join(" ").split(/\s+/).filter(Boolean).length;

// tipo do roteiro → { primitiva, html(cena, imagem), texto(cena) (o que se lê na tela), itens(cena) }
export const TIPOS = {
  titulo: {
    primitiva: "Title",
    html: (c) => cab(c) + (c.subtitulo ? `<div class="texto apagado sub">${esc(c.subtitulo)}</div>` : ""),
    texto: (c) => [c.etiqueta, c.titulo, c.subtitulo],
    itens: () => 0,
  },
  topicos: {
    primitiva: "BulletList",
    html: (c) => cab(c) + c.itens.map((t) => `<div class="caixa item"><div class="texto cresce">${esc(t)}</div></div>`).join(""),
    texto: (c) => [c.titulo, c.itens],
    itens: (c) => c.itens.length,
  },
  numero: {
    primitiva: "CountUp",
    // --chars: tamanho do valor final, para a fonte encolher e caber numa linha (tokens.css).
    html: (c) => cab(c) + `<div class="numero" style="--chars: ${numeroFinal(c).length}">${esc(c.prefixo)}0${esc(c.sufixo)}</div>` +
      (c.rotulo ? `<div class="texto apagado rotulo">${esc(c.rotulo)}</div>` : ""),
    texto: (c) => [c.titulo, c.rotulo, "número"],
    itens: () => 4, // a contagem leva ~2 s
  },
  ranking: {
    primitiva: "Ranking",
    html: (c) => cab(c) + c.itens.map(([nome, valor], i) =>
      `<div class="caixa item"><div class="selo">${i + 1}</div><div class="texto cresce">${esc(nome)}</div>` +
      (valor != null ? `<div class="texto destaque">${esc(valor)}</div>` : "") + `</div>`).join(""),
    texto: (c) => [c.titulo, c.itens.map((i) => i.join(" "))],
    itens: (c) => c.itens.length + 1,
  },
  comparar: {
    primitiva: "Compare",
    html: (c) => cab(c) + `<div class="lado">` + [c.antes, c.depois].map((l) =>
      `<div class="caixa"><div class="texto apagado">${esc(l.rotulo)}</div><div class="titulo destaque">${esc(l.valor)}</div></div>`).join("") + `</div>`,
    texto: (c) => [c.titulo, c.antes.rotulo, c.antes.valor, c.depois.rotulo, c.depois.valor],
    itens: () => 2,
  },
  fluxo: {
    primitiva: "StepFlow",
    html: (c) => cab(c) + `<div class="etapas">` + c.etapas.map((t, i) =>
      (i ? `<div class="conector"></div>` : "") +
      `<div class="caixa item"><div class="selo">${i + 1}</div><div class="texto cresce">${esc(t)}</div></div>`).join("") + `</div>`,
    texto: (c) => [c.titulo, c.etapas],
    itens: (c) => c.etapas.length * 1.5,
  },
  print: {
    primitiva: "ScreenshotCard",
    html: (c, img) => cab(c) + `<div class="quadro"><img src="${esc(img)}" alt=""></div>`,
    texto: (c) => [c.titulo],
    itens: () => 3,
  },
  imagem: {
    primitiva: "ImageKenBurns",
    html: (c, img) => `<div class="imagem-cheia"><img src="${esc(img)}" alt=""></div>` +
      (c.legenda_tela ? `<div class="legenda-tela">${esc(c.legenda_tela)}</div>` : ""),
    texto: (c) => [c.legenda_tela],
    itens: () => 2,
  },
  frase: {
    primitiva: "MaskReveal",
    html: (c) => (c.etiqueta ? `<div class="etiqueta">${esc(c.etiqueta)}</div>` : "") +
      c.linhas.map((l) => `<div class="titulo revela">${esc(l)}</div>`).join(""),
    texto: (c) => [c.linhas],
    itens: (c) => c.linhas.length,
  },
};

// Duração mínima da cena: tempo de leitura (palavras ÷ 3 + 0,5 s) + entrada dos itens + respiro.
export function duracaoMinima(c) {
  const t = TIPOS[c.tipo];
  return +(palavras(...t.texto(c).filter(Boolean)) / 3 + 0.5 + t.itens(c) * 0.5 + 0.6).toFixed(2);
}
