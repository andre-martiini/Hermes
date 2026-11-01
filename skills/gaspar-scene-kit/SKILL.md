---
name: gaspar-scene-kit
description: Kit de cena do Gaspar Vídeo (motor HyperFrames) — a única forma permitida de desenhar cartões e cenas animadas (títulos, tópicos, número que conta, ranking, comparação, fluxo de etapas, print, imagem com Ken Burns, frase revelada) em 9:16 e 16:9. Carregue antes de gerar qualquer cena nas skills gaspar-video e gaspar-video-sobreposicao quando GASPAR_VIDEO_ENGINE=hyperframes, ou quando o André pedir cartões animados no padrão novo.
---

# Gaspar scene kit

O Claude não desenha cena à mão: escreve um **roteiro JSON** e `scripts/montar.mjs` gera o projeto
HyperFrames só com as primitivas do kit, passa o **lint de cena** e renderiza o MP4. Tokens, curvas e
durações moram em código (`kit/tokens.css`, `kit/kit.js`), não no prompt.

**Ambiente (uma vez por máquina):** Node 20+, `npm install` nesta pasta, FFmpeg com ffprobe
(`winget install --id Gyan.FFmpeg -e`; o montador acha a pasta do winget mesmo sem PATH).

```
node scripts/montar.mjs roteiro.json SAIDA --so-html   # projeto + lint, grátis, segundos
node scripts/montar.mjs roteiro.json SAIDA --revisao   # + PNG de cada cena assentada (SAIDA/<formato>/revisao)
npm test                                               # testes do kit e do lint
```

## Regras duras (o lint recusa o render se quebrar)

1. **Só primitivas do kit.** Tipos do roteiro → primitiva: `titulo`→Title, `topicos`→BulletList,
   `numero`→CountUp, `ranking`→Ranking, `comparar`→Compare, `fluxo`→StepFlow, `print`→ScreenshotCard,
   `imagem`→ImageKenBurns, `frase`→MaskReveal. Precisa de outra? Acrescente ao kit (primitivas.mjs +
   kit.js + MOTION_ROLES), nunca na cena.
2. **Só as 4 curvas de `kit.js`:** `enter` = cubic-bezier(0.16, 1, 0.3, 1); `exit` = ease-in com 65% da
   entrada; `emphasis` = back.out leve; `settle` = ease-out longo. Nada de `linear`, `ease` próprio,
   `gsap.`, `interpolate` ou `spring` na cena.
3. **Cor e fonte só dos tokens:** paleta da casa (azul-marinho, âmbar, 2 de apoio), Inter (OFL, embutida,
   igual em qualquer máquina), 3 tamanhos (número, título, texto).
4. **No máximo 2 transições por vídeo:** `fade` (padrão) e `wipe` (`"transicao": "wipe"` na cena que entra).
5. **Números sempre `numero`** (conta até o valor, algarismos de largura fixa, encolhe para caber numa linha).
6. **Imagens sempre `imagem`** (Ken Burns 1,0→1,08 em 5 s) **ou `print`** (cartão com deriva lenta).
7. **Safe area 9:16:** 15% em cima e 20% embaixo ficam livres (a base é da legenda). 16:9: fluxo na horizontal.
8. **Tempo de leitura:** cada cena dura no mínimo palavras ÷ 3 + 0,5 s + a entrada dos itens; o montador
   alonga e avisa se o roteiro pedir menos.
9. **SFX:** cada evento relevante deixa um marcador em `window.__sfx` (`Title.enter`, `CountUp.tick`,
   `Ranking.item`, `StepFlow.advance`, `Compare.reveal`, `Wipe.transition`…), no pico da curva. A Fase 3
   transforma isso em som.

## Roteiro

```json
{
  "titulo": "Gaspar Vídeo - Tema",
  "formato": "vertical",                         // vertical | horizontal | ambos
  "cenas": [
    {"tipo": "titulo",   "etiqueta": "...", "titulo": "...", "subtitulo": "..."},
    {"tipo": "topicos",  "titulo": "...", "itens": ["...", "..."], "em": [1.2, 2.5]},
    {"tipo": "numero",   "etiqueta": "...", "titulo": "...", "valor": 1250000, "prefixo": "R$ ", "sufixo": "", "casas": 0, "rotulo": "..."},
    {"tipo": "ranking",  "titulo": "...", "itens": [["nome", "42%"], ["nome", "31%"]]},
    {"tipo": "comparar", "titulo": "...", "antes": {"rotulo": "Antes", "valor": "12 dias"}, "depois": {"rotulo": "Agora", "valor": "2 dias"}},
    {"tipo": "fluxo",    "titulo": "...", "etapas": ["...", "..."], "transicao": "wipe"},
    {"tipo": "print",    "titulo": "...", "imagem": "tela.png"},
    {"tipo": "imagem",   "imagem": "arte.png", "legenda_tela": "..."},
    {"tipo": "frase",    "etiqueta": "...", "linhas": ["...", "..."]}
  ]
}
```

- `duracao` (s) é opcional; `em` (s desde o início da cena, um por item) sincroniza cada item com a fala.
- Até 5 itens por cena, frases de até ~6 palavras. Uma ideia por cena.
- Dados de pessoas: nada real; valores de exemplo marcados como fictícios.
- Exemplo completo: `exemplos/cartoes.json` (os 3 cartões de teste da Fase 1).

## Revisão

Abra `SAIDA/<formato>/revisao/contact-sheet.jpg` e confira: nada cortado ou fora da safe area, número
numa linha, item ativo em âmbar, cena assentada. Só então entregue.

## Motor

`GASPAR_VIDEO_ENGINE=legacy|hyperframes`. O padrão continua `legacy` (motion.py com voz, legenda e trilha)
até o kit ganhar voz e legendas alinhadas (Fase 2) e som (Fase 3).
