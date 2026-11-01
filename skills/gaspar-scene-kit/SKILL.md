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
  reconhecimento e corrige a grafia de nomes próprios e siglas (Redtec → Reditec).
- **Motor da transcrição** (`GASPAR_ASR`): `whisper` (padrão) ou `parakeet` (NVIDIA Parakeet TDT 0.6B v3 int8 via
  `sherpa-onnx`, pesos nos releases do GitHub; serve onde o Hugging Face é bloqueado, e o whisper cai nele
  sozinho se não carregar). `PY -m pip install sherpa-onnx`; o modelo (~490 MB) baixa na 1ª vez.
- Legenda revisada à mão: com `"legendas_revisadas": true`, `SAIDA/legendas.json` nunca é sobrescrito (se ficar
  mais velho que a gravação, o montador avisa em vez de transcrever de novo).
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
- **Título de abertura:** `{"tipo": "titulo_atras", "etiqueta": "...", "titulo": "MAGO"}`. O montador recorta a
  pessoa (o mesmo alfa suave do gaspar-v2v, ~3 quadros/s na CPU, com cache) e **escolhe o modo antes do render**,
  medindo a caixa real do texto no Chrome contra a máscara da pessoa a cada 0,1 s da janela do cartão:
  1. `atras` — entre o fundo e a pessoa, apoiado no topo da cabeça (p10 na janela). Só se cada letra ficar
     ≥ 70% visível (p90) e o título couber inteiro na tela e na safe area (o título atrás pode subir até 5%);
  2. `abaixo` — vidro escuro entre o queixo (p90 do rosto) e a legenda, sem tocar o rosto;
  3. `antes` — cartão cheio de 1,2 s sobre a gravação desfocada; só se a fala começar depois dele;
  4. `topo` — painel no topo, se houver espaço acima da cabeça.
  A decisão (e por que os outros modos foram recusados) sai no terminal e em `gates.json` (`titulos`). Nenhum
  serve → o montador não renderiza e diz quanto a cabeça ocupa do quadro (regrave mais afastado, ou faça uma pausa
  de 1 s antes de falar). `"modo": "atras|abaixo|antes|topo"` força um modo, mas os gates valem igual. A fonte
  encolhe medida no DOM até caber (nada de tamanho fixo no roteiro).
- **Ilustração animada:** `"animar": true` numa cena `imagem` → o Veo 3.1 Lite anima a própria ilustração
  (elementos flutuando, leve aproximação; mesmo estilo, sem texto novo). ~US$ 0,20 por 4 s, com cache por imagem
  (`SAIDA/animacoes/anim-<sha1(imagem + "aspecto|segundos")[:12]>.mp4`). Precisa de
  `GOOGLE_APPLICATION_CREDENTIALS` (conta de serviço do Hermes). Sem Veo (falhou, ou `--animacao local`):
  `animar_local.py` (partículas e câmera, grátis, arquivo `...-local.mp4`) e um **aviso** no terminal — diga ao
  André que não foi o Veo.
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
- **Ambiente** (cafeteria, auditório, rua…): `"ambiente": {"prompt": "busy coffee shop ambience…", "nivel_db": -26,
  "fade": 1.0}` no roteiro (vale o vídeo todo; `inicio`/`fim` para uma janela), numa cena (vale a janela dela), ou
  uma lista. `scripts/ambiente.py` gera um trecho de até 20 s **em loop sem emenda** no ElevenLabs Sound Effects v2
  via fal (US$ 0,002/s: ~US$ 0,04 por vídeo; cai no ElevenLabs direto se o fal falhar) e guarda na biblioteca
  `~/.tutorial-sistema/ambientes/` (catálogo com prompt, motor, data e licença: o mesmo prompt não paga de novo).
  `"arquivo": "x.wav"` usa um som seu. Mistura: passa-alta 120 Hz e passa-baixa 8 kHz, −24 a −28 dB abaixo da voz,
  ducking leve pela fala e fade. Prompt em inglês rende melhor. `--sem-ambiente` desliga.
- **Loudness** −14 LUFS (loudnorm em dois passes) + limitador de true-peak a 4× a taxa (teto −3 dBFS), porque o
  loudnorm linear sozinho deixa passar estalos; o gate mede o **AAC final**.
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
- **Composição (sobreposição, antes do render, bloqueiam):** `titulo-cortado` (caixa real de qualquer texto fora de
  0–1080 × 0–1920), `titulo-oculto` (letra do título atrás com < 70% visível em p90), `rosto-coberto` (cartão ou
  painel sobre a caixa do rosto do MediaPipe em qualquer instante da janela; exceto `print` com `"layout":
  "cheio"` até 8 s), `titulo-sem-modo` (nenhum modo do título cabe). A máscara vem do recorte da pessoa
  (`--sem-recorte` desliga recorte e estes gates).
- **Depois do render (falham o montar):** `check-duracao` (vídeo = áudio ± 100 ms; nenhuma cena abaixo do
  tempo de leitura), `check-audio` (−14 ± 1 LUFS, true peak ≤ −1,5 dBTP, nenhum silêncio > 1,5 s no meio) e
  `check-quadros` (nos quadros reais em 0,5 s, meio e fim de cada cartão: o rosto continua o da gravação —
  correlação ≥ 0,6 — e nenhum texto novo encosta na borda).
- **Prévia:** `previa-10/50/90.png` em `SAIDA/<formato>/` — anexe ao diário da ação antes da entrega.
- **Entrega:** MP4 final no Drive ou anexado à ação (`preparar_upload` + `anexar_arquivo`), com link e custo
  no diário. Nunca só o caminho local.

## Revisão

Abra `SAIDA/<formato>/revisao/contact-sheet.jpg` e confira: nada cortado ou fora da safe area, número
numa linha, item ativo em âmbar, cena assentada. A folha traz também, por título, o **pior quadro** (maior oclusão
pela pessoa). Os gates passarem não basta: olhe a folha. Só então entregue.

## Ambiente de execução

- Render longo: `node scripts/montar.mjs roteiro.json SAIDA --detach` roda solto do terminal (log em
  `SAIDA/montar.log`); sem isso, um terminal/ferramenta que encerra o processo pai mata o render
  (`render_cancelled_parent_exited`).
- Sem acesso ao download do `chrome-headless-shell` (nuvem com lista de hosts): `HYPERFRAMES_BROWSER_PATH` e
  `PRODUCER_HEADLESS_SHELL_PATH` apontando um Chrome instalado (ex.: `/usr/bin/google-chrome`); os gates usam o
  mesmo Chrome.
- Pré-requisitos da sobreposição, com cache em SAIDA (refeitos se a gravação for mais nova): `legendas.json`
  (transcrição) e `pessoa.webm` + `rastro.json` (recorte e rosto, via `../gaspar-v2v/scripts/efeitos.py recortar`).

## Motor

`GASPAR_VIDEO_ENGINE=legacy|hyperframes`. O padrão continua `legacy` (motion.py com voz, legenda e trilha)
até a revisão do André nos vídeos de teste das Fases 2 e 3.
