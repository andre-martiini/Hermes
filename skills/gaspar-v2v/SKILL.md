---
name: gaspar-v2v
description: Troca o cenário e a roupa de um vídeo do André falando, mantendo rosto, gestos e voz idênticos (video-to-video com referência, em cortes de 5–10 s com "mundos" diferentes, remontados sobre o áudio original). Use quando o André mandar uma gravação dele e pedir outro cenário, outra roupa, "mundos", "aquele efeito de trocar o fundo a cada frase", Reels com cenários diferentes. Custa dólares (fal.ai): rascunho barato, aprovação dele, depois o final.
---

# Gaspar V2V e efeitos — o André fica igual

> **Regra do André (01/11/2026): o rosto dele nunca é regenerado.** V2V de quadro inteiro (Wan VACE,
> Kling sem devolver o rosto) ficou "artificial demais" e foi reprovado. Use sempre um destes, que mantêm
> os pixels originais do rosto, da boca e a voz:
>
> | Quer | Use | Custo |
> |---|---|---|
> | Trocar o cenário a cada corte | **Recorte + fundo** (abaixo) — aprovado | ~US$ 0,04 por cenário |
> | Efeito na mão (fogo, magia, raio, holograma, logo…) | `efeitos.py elemento` + `efeitos.py mao` | ~US$ 0,24 por elemento (reutilizável) |
> | Roupa/estilo (mago, terno, armadura…) | `efeitos.py transformar` (gera e **devolve o rosto original**) | Kling O3 Pro ~US$ 0,17/s |
>
> Os efeitos combinam (ex.: `transformar` e depois `mao` sobre o resultado = mago com fogo na mão).
> O fluxo V2V de quadro inteiro abaixo fica só para cenas sem o rosto do André.

## Efeitos com o rosto intacto (`scripts/efeitos.py`)

PY = venv da tutorial-sistema (`~/.tutorial-sistema/.venv`, com mediapipe 1.2 e google-cloud-firestore/storage);
modelos do MediaPipe em `~/.tutorial-sistema/modelos/` (hand_landmarker.task, face_landmarker.task).

- `efeitos.py rastrear video SAIDA` — mão (21 pontos) e rosto (478) por quadro, grátis, com cache.
- `efeitos.py elemento "descrição" SAIDA` — elemento animado isolado sobre preto (imagem no fal + 4 s no Veo Lite).
- `efeitos.py mao video elemento.mp4 SAIDA [--de 1.9 --ate 4.6 | --gatilho visivel|acima] [--escala 2.8]
  [--cor 255,140,40] [--dedos-na-frente]` — o elemento segue a palma, acende em 8 quadros, ilumina a cena.
  `--dedos-na-frente` para a pose de "segurar por baixo"; com a palma de frente para a câmera, deixe sem.
- `efeitos.py transformar video "o que muda" SAIDA [--ref figurino.png] [--modelo kling-pro|kling]` — a IA gera a
  roupa/estilo; o rosto original volta por cima (máscara oval recuada na testa para chapéu, alinhada ao nariz da
  cabeça gerada a cada quadro, cor casada na borda). Entrada de 3–10 s. O áudio é sempre o original.
- **Grave para efeito:** fundo neutro, luz frontal, gesto claro e devagar, mão sem cobrir o rosto.

## Recorte + fundo (troca de cenário)

`hyperframes remove-background base30.mp4 -o pessoa.mov` (local, ~1,3 quadro/s na CPU) → cenários gerados
(nano-banana 9:16, "no people", fundo desfocado) com aproximação lenta → overlay com a borda do recorte afinada
(`erosion` + gama no alfa, tira o halo da parede clara) → áudio original. Ver `saida/v2v/recorte` no histórico
do plano (01/11/2026).

# (Legado) V2V de quadro inteiro — só para cenas sem o rosto do André

Cada corte de 5–10 s (em fim de frase, nunca no meio da palavra) ganha um "mundo" (cenário + roupa) com
prompt e imagem de referência; os clipes gerados são remontados sobre o **áudio original contínuo**.
Depois, legenda e cartões do `gaspar-scene-kit` por cima (**ordem fixa: V2V primeiro**, para a IA não
deformar texto).

`PY` = `functions\venv\Scripts\python.exe` do Hermes (Firestore/Storage, credencial
`GOOGLE_APPLICATION_CREDENTIALS` = `firebase_service_account_key.json`); FFmpeg no PATH. A transcrição
usa o `legendas.py` do gaspar-scene-kit (venv da tutorial-sistema com faster-whisper).

## Fluxo

1. **Gravação**: pegue o MP4 (Drive → baixe com a credencial do dono, `video/entrega.drive_do_dono`).
   Bom para V2V: fundo neutro, roupa lisa, movimento moderado, mãos pouco à frente do rosto.
2. **Mundos** (`mundos.json`): `[{"nome", "cenario", "roupa"}]`, descrições em inglês. Pergunte ao André
   quantos e quais; sem preferência, 2 contrastantes.
3. `PY scripts/v2v.py preparar gravacao.mp4 mundos.json SAIDA` — grátis: áudio, transcrição, cortes e
   `SAIDA/segments.json` (início, fim, texto, mundo). Mostre a tabela de cortes.
4. `PY scripts/v2v.py rascunho SAIDA --task <id da ação>` — Wan VACE 480p (~US$ 0,05/s; Reel de 30 s ≈
   US$ 1,50) + 1 referência por mundo. Gera `SAIDA/rascunho.mp4`. **Suba ao Drive/anexe à ação e PARE:
   o André aprova o look e os prompts.** Ajuste `mundos.json`/`segments.json` e refaça só o que mudou
   (apague `SAIDA/rascunho/corte-N.mp4` do corte a refazer).
5. `PY scripts/v2v.py final SAIDA --task <id> [--pro]` — Kling O3 Std (~US$ 0,126/s; Pro 0,168) com
   `keep_audio` e a referência em `@Image1`. Acima de US$ 5 por corte o script para e mostra o custo:
   com o OK do André, repita com `--aprovado-ate <valor>`. Gera `SAIDA/final.mp4`.
6. **Legendas e cartões**: roteiro do gaspar-scene-kit com `"gravacao": "SAIDA/final.mp4"` (modo
   sobreposição) → MP4 com legenda palavra a palavra, cartões, som e LUT, passando pelos gates.
7. **Entrega**: MP4 no Drive/anexado à ação; no diário, o custo real (soma em `videoJobs` com o `task_id`).

## Regras

- Remux obrigatório (o `remux()` já faz): cada clipe aparado à duração exata do corte, sobre o áudio
  original — corrige modelo que regera som ou muda fps.
- Planeje 2–3 tentativas nos cortes difíceis (mãos, texto na roupa, movimento rápido).
- Gemini Omni é 2ª opção e recusa rosto reconhecível: não usar para o André sem testar.
- Custos: tabela em `functions/video/fal.py` (`config/precos_fal` no Firestore sobrescreve); confira o
  billing do fal ao fim do mês.
