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

## Voz e legendas (Fase 2)

- **Motion** (cenas com `"narracao"`): o montador chama `narrar.py` (voz Aoede, ~US$ 0,15/min, cache) e
  `legendas.py motion` (whisper local só para o tempo; **o texto é o do roteiro**, zero erro de grafia).
  Cada cena dura a fala + respiro; cada item entra quando a fala o cita (ou use `"em"`).
- **Sobreposição** (`"gravacao": "video.mp4"` no roteiro): a gravação fica no fundo com o som original, a
  legenda vem da fala transcrita (`legendas.py fala`) e cada cartão entra no topo, em painel de vidro,
  quando a fala diz o seu `"quando"` (frase exata) ou em `"inicio"` (s). `"chaves": ["Ifes", ...]` ajuda o
  whisper com nomes próprios.
- `"legenda_estilo"`: `"palavra"` (300 ms, padrão na sobreposição/Reels) ou `"frase"` (1200 ms, padrão no
  motion/aula). `"legenda": false` desliga.
- Palavras com confiança < 0,6 saem listadas no terminal: corrija em `SAIDA/legendas.json`, rode de novo
  (o alinhamento só refaz se a narração ou a gravação mudar) e registre a lista no diário da ação.
- Requisitos: a venv da tutorial-sistema (`preparar.py` → PY) com `faster-whisper` (`PY -m pip install
  faster-whisper==1.1.1`); modelo em `GASPAR_WHISPER_MODELO` (padrão `small`; `medium` é mais exato).

## Estilo "apresentador + painel" (sobreposição)

Técnicas do vídeo de referência do André (01/11/2026), todas compostas sobre a gravação (rosto intacto):
- **Apresentador em cartão:** `"layout": "dividido"` em qualquer cena da sobreposição. A gravação inteira encolhe
  para um cartão em retrato na metade de baixo (`"escala": 0.6` = tamanho; `"foco": 0.06` = recorte no topo) e o
  painel da cena ocupa a parte de cima (`imagem` preenche o painel; listas, números, fluxos em tamanho compacto).
  Volta à tela cheia no fim da cena.
- **Título atrás da pessoa:** `{"tipo": "titulo_atras", "etiqueta": "...", "titulo": "2.0"}`. O montador recorta a
  pessoa (HyperFrames `remove-background`, ~8 min de CPU por 20 s, com cache), mede o topo da cabeça e apoia o
  título nele: só o terço de baixo das letras fica atrás (exceção à safe area: o título pode subir até 5%).
- **Fechamento:** `{"tipo": "chamada"}` desfoca e escurece a cena (ex.: no "valeu" final). `"titulo"` e
  `"botao"` são opcionais (o André prefere sem botão); com texto, comece cedo o bastante para a leitura.
- Exemplo: `exemplos/estilo-apresentador.json` (título atrás → painel com ilustração → lista →
  chamada).

## Som e cor (Fase 3)

Depois do render, o `pos.mjs` (chamado pelo montador) faz no FFmpeg:
- **SFX** nos marcadores do kit (`kit/sfx-map.json`: `Title.enter`→whoosh-curto, `CountUp.tick`→tick,
  `Ranking.item`→pop, `StepFlow.advance`→swipe, `Compare.reveal`→impacto-suave…), com o **pico do som no
  pico da curva**, a −12 dB da voz. Biblioteca: `assets/sfx/` (20 sons ElevenLabs, ≤ 0,8 s; refazer um:
  `scripts/gerar_sfx.py --refazer nome`).
- **Trilha** (a da tutorial-sistema, ou `"trilha": "x.m4a"`; `false` desliga) com **ducking** de ~9 dB sob a voz.
- **Loudness** −14 LUFS / −1,5 dBTP (loudnorm em dois passes); o montador imprime a medição EBU R128.
- **LUT de marca** `assets/lut/gaspar.cube` (quente leve, contraste médio, pretos levantados) em todo vídeo;
  os botões ficam em `scripts/gerar_lut.py`. `"lut": false` ou `--sem-lut` desliga.
- Transições são do kit (fade/wipe, no HyperFrames), não `xfade`. Requer FFmpeg completo (winget Gyan.FFmpeg).

## Quality gates (Fase 6)

O montador não entrega vídeo que não passe (`scripts/gates.mjs`; relatório em `SAIDA/<formato>/gates.json`):
- **Antes do render (bloqueiam; `--forcar` só para depurar):** `lint-cena` (curva/cor/fonte fora do kit);
  `check-legibilidade` (texto fora da safe area 9:16 — 15% em cima, 20% embaixo —, fonte < 48 px em
  1080×1920, contraste < 4,5:1), medido no Chrome com cada cena assentada; `check-legendas` (motion: legenda
  = narração palavra por palavra; sobreposição: palavra com confiança < 0,6 só passa marcada `"revisado": true`
  em legendas.json ou com `"legendas_revisadas": true` no roteiro).
- **Depois do render (falham o montar):** `check-duracao` (vídeo = áudio ± 100 ms; nenhuma cena abaixo do
  tempo de leitura) e `check-audio` (−14 ± 1 LUFS, true peak ≤ −1,5 dBTP, nenhum silêncio > 1,5 s no meio).
- **Prévia:** `previa-10/50/90.png` em `SAIDA/<formato>/` — anexe ao diário da ação antes da entrega.
- **Entrega:** MP4 final no Drive ou anexado à ação (`preparar_upload` + `anexar_arquivo`), com link e custo
  no diário. Nunca só o caminho local.

## Revisão

Abra `SAIDA/<formato>/revisao/contact-sheet.jpg` e confira: nada cortado ou fora da safe area, número
numa linha, item ativo em âmbar, cena assentada. Só então entregue.

## Motor

`GASPAR_VIDEO_ENGINE=legacy|hyperframes`. O padrão continua `legacy` (motion.py com voz, legenda e trilha)
até a revisão do André nos vídeos de teste das Fases 2 e 3.
