/* Gaspar scene kit — movimento. Única fonte de curvas, durações e animações das cenas.
 *
 * Cada primitiva declara o papel de movimento que usa (MOTION_ROLES); nenhuma cena chama
 * gsap direto: o index.html gerado pelo montar.mjs só chama Kit.montar(). O lint-cena recusa
 * qualquer `ease`, `gsap.` ou cor fora daqui e do tokens.css.
 *
 * Determinístico (seek(t)): nada de Date.now, Math.random ou rede.
 */
(function () {
  gsap.registerPlugin(CustomEase);

  // Exatamente 4 curvas. Proibidas as demais.
  const EASE = {
    enter: CustomEase.create("enter", "0.16,1,0.3,1"),
    exit: "power2.in",
    emphasis: "back.out(1.7)",
    settle: "power3.out",
  };

  // Durações em segundos. A saída tem 65% da entrada.
  const T = {
    entrada: 0.45,
    saida: 0.45 * 0.65,
    stagger: 0.06,
    entreItens: 0.5,
    enfase: 0.35,
    assenta: 1.2,
    contagem: 2.0,
    // Tempo de leitura de um texto na tela: palavras ÷ 3 + 0,5 s.
    leitura: (palavras) => palavras / 3 + 0.5,
  };

  // Instante do "pico" de cada curva, em fração da duração: é onde o SFX deve cair (Fase 3).
  const PICO = { enter: 0.2, emphasis: 0.55, settle: 0.3, exit: 0.9 };

  const MOTION_ROLES = {
    Title: { entra: "enter", sai: "exit" },
    BulletList: { entra: "enter", ativo: "emphasis" },
    CountUp: { entra: "enter", conta: "settle" },
    Ranking: { entra: "enter", primeiro: "emphasis" },
    Compare: { entra: "enter", revela: "emphasis" },
    StepFlow: { entra: "enter", avanca: "emphasis" },
    ScreenshotCard: { entra: "enter", deriva: "settle" },
    ImageKenBurns: { zoom: "settle" },
    MaskReveal: { revela: "enter" },
    Wipe: { transicao: "enter" },
  };

  // Marcadores de SFX: {t, evento}. A Fase 3 mapeia evento → som (sfx-map).
  const sfx = [];
  const marca = (t, evento, curva = "enter", dur = T.entrada) =>
    sfx.push({ t: +(t + PICO[curva] * dur).toFixed(3), evento });

  const $ = (raiz, sel) => Array.from(raiz.querySelectorAll(sel));

  function entra(tl, alvos, t, { dx = 0, dy = 60, stagger = T.stagger } = {}) {
    if (!alvos.length) return;
    tl.fromTo(alvos, { opacity: 0, x: dx, y: dy },
      { opacity: 1, x: 0, y: 0, duration: T.entrada, ease: EASE.enter, stagger }, t);
  }

  function enfatiza(tl, el, t) {
    tl.fromTo(el, { scale: 1 }, { scale: 1.08, duration: T.enfase / 2, ease: EASE.emphasis, yoyo: true, repeat: 1 }, t);
  }

  // Cabeçalho comum (etiqueta + título): a 1ª cena já começa assentada, para o quadro 0 não ficar vazio.
  function cabecalho(tl, sec, t0, primeira) {
    const alvos = $(sec, ".cab");
    if (primeira) return t0 + 0.1;
    entra(tl, alvos, t0 + 0.1);
    marca(t0 + 0.1, "Title.enter");
    return t0 + 0.1 + T.entrada;
  }

  // Instante de entrada do item i: `em` do roteiro (relativo à cena) ou em sequência.
  const quando = (c, i, base) => (c.em && c.em[i] != null ? c.t0 + c.em[i] : base + i * T.entreItens);

  const P = {
    Title(tl, sec, c) {
      if (c.primeira) return;
      entra(tl, $(sec, ".cab, .sub"), c.t0 + 0.1);
      marca(c.t0 + 0.1, "Title.enter");
    },

    BulletList(tl, sec, c) {
      const base = cabecalho(tl, sec, c.t0, c.primeira) + 0.15;
      $(sec, ".item").forEach((el, i, todos) => {
        const t = quando(c, i, base);
        entra(tl, [el], t, { dx: -80, dy: 0 });
        tl.set(todos, { className: "caixa item" }, t);
        tl.set(el, { className: "caixa item ativo" }, t);
        marca(t, "BulletList.item");
      });
    },

    CountUp(tl, sec, c) {
      const base = cabecalho(tl, sec, c.t0, c.primeira);
      const el = sec.querySelector(".numero");
      entra(tl, $(sec, ".numero, .rotulo"), base);
      const fmt = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: c.casas || 0, maximumFractionDigits: c.casas || 0 });
      const n = { v: 0 };
      const escreve = () => { el.textContent = (c.prefixo || "") + fmt.format(n.v) + (c.sufixo || ""); };
      escreve();
      const t = base + 0.1;
      tl.to(n, { v: c.valor, duration: T.contagem, ease: EASE.settle, onUpdate: escreve }, t);
      // Tique do contador: no máximo 8 por segundo, mais densos no início (onde a curva corre).
      const tiques = Math.min(12, Math.floor(T.contagem * 8));
      for (let k = 0; k < tiques; k++) sfx.push({ t: +(t + T.contagem * (1 - Math.cbrt(1 - k / tiques))).toFixed(3), evento: "CountUp.tick" });
    },

    Ranking(tl, sec, c) {
      const base = cabecalho(tl, sec, c.t0, c.primeira) + 0.15;
      const itens = $(sec, ".item");
      itens.forEach((el, i) => {
        const t = quando(c, i, base);
        entra(tl, [el], t, { dx: -120, dy: 0 });
        marca(t, "Ranking.item");
      });
      const fim = quando(c, itens.length - 1, base) + T.entrada + 0.2;
      enfatiza(tl, itens[0].querySelector(".selo"), fim);
      marca(fim, "Ranking.primeiro", "emphasis", T.enfase);
    },

    Compare(tl, sec, c) {
      const base = cabecalho(tl, sec, c.t0, c.primeira) + 0.15;
      const [a, b] = $(sec, ".lado .caixa");
      entra(tl, [a], quando(c, 0, base), { dy: 40 });
      const t = quando(c, 1, base + 0.4);
      tl.fromTo(b, { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: T.entrada, ease: EASE.emphasis }, t);
      tl.set(b, { className: "caixa ativo" }, t);
      marca(t, "Compare.reveal", "emphasis");
    },

    StepFlow(tl, sec, c) {
      const base = cabecalho(tl, sec, c.t0, c.primeira) + 0.15;
      const etapas = $(sec, ".item");
      entra(tl, $(sec, ".item, .conector"), base, { dy: 40, stagger: T.entreItens / 2 });
      const inicio = base + (etapas.length * 2 - 1) * (T.entreItens / 2) + 0.2;
      etapas.forEach((el, i) => {
        const t = c.em && c.em[i] != null ? c.t0 + c.em[i] : inicio + i * 0.7;
        tl.set(etapas, { className: "caixa item" }, t);
        tl.set(el, { className: "caixa item ativo" }, t);
        enfatiza(tl, el.querySelector(".selo"), t);
        marca(t, "StepFlow.advance", "emphasis", T.enfase);
      });
    },

    ScreenshotCard(tl, sec, c) {
      const base = cabecalho(tl, sec, c.t0, c.primeira);
      const q = sec.querySelector(".quadro");
      tl.fromTo(q, { opacity: 0, y: 80, scale: 0.94 }, { opacity: 1, y: 0, scale: 1, duration: T.entrada, ease: EASE.enter }, base);
      tl.to(q, { scale: 1.03, duration: Math.max(1, c.fim - base - 0.5), ease: EASE.settle }, base + T.entrada);
      marca(base, "ScreenshotCard.enter");
    },

    // Escala 1,0 → 1,08 em 5 s; cena mais longa mantém a mesma velocidade.
    ImageKenBurns(tl, sec, c) {
      const img = sec.querySelector(".imagem-cheia img");
      const dur = c.fim - c.t0;
      tl.fromTo(img, { scale: 1 }, { scale: 1 + 0.016 * dur, duration: dur, ease: EASE.settle }, c.t0);
      if (sec.querySelector(".legenda-tela")) {
        entra(tl, $(sec, ".legenda-tela"), c.t0 + 0.4, { dy: 30 });
        marca(c.t0 + 0.4, "Title.enter");
      }
    },

    // Texto revelado por retângulo (clip-path), da esquerda para a direita.
    MaskReveal(tl, sec, c) {
      $(sec, ".revela").forEach((el, i) => {
        const t = quando(c, i, c.t0 + 0.2);
        tl.fromTo(el, { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: T.entrada * 1.4, ease: EASE.enter }, t);
        marca(t, "MaskReveal.reveal", "enter", T.entrada * 1.4);
      });
    },
  };

  // Transições: no máximo 2 tipos por vídeo — "fade" (padrão) e "wipe". O wipe pertence à cena
  // que entra: ela varre por cima da anterior, que o montar.mjs prolonga por T.entrada.
  function transicao(tl, sec, c, proxima) {
    if (proxima && proxima.transicao === "wipe") return;
    tl.to(sec, { opacity: 0, duration: T.saida, ease: EASE.exit }, c.fim - T.saida);
  }
  function wipeEntra(tl, sec, c) {
    tl.fromTo(sec, { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: T.entrada, ease: EASE.enter }, c.t0);
    marca(c.t0, "Wipe.transition");
  }

  // `dadosId`: o <script type="application/json"> que o montar.mjs escreve com o tempo de cada cena.
  function montar(dadosId, compId) {
    const { cenas } = JSON.parse(document.getElementById(dadosId).textContent);
    const tl = gsap.timeline({ paused: true });
    cenas.forEach((c, i) => {
      const sec = document.getElementById("cena-" + i);
      const anima = P[c.primitiva];
      if (!anima) throw new Error("Primitiva fora do kit: " + c.primitiva);
      if (c.transicao === "wipe" && i > 0) wipeEntra(tl, sec, c);
      anima(tl, sec, c);
      if (i < cenas.length - 1) transicao(tl, sec, c, cenas[i + 1]);
    });
    sfx.sort((a, b) => a.t - b.t);
    window.__sfx = sfx;
    window.__timelines = window.__timelines || {};
    window.__timelines[compId] = tl;
    tl.seek(0);
    return tl;
  }

  window.Kit = { EASE, T, PICO, MOTION_ROLES, montar };
})();
