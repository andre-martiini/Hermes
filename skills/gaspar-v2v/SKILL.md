---
name: gaspar-v2v
description: Troca o cenário e a roupa de um vídeo do André falando, mantendo rosto, gestos e voz idênticos (video-to-video com referência, em cortes de 5–10 s com "mundos" diferentes, remontados sobre o áudio original). Use quando o André mandar uma gravação dele e pedir outro cenário, outra roupa, "mundos", "aquele efeito de trocar o fundo a cada frase", Reels com cenários diferentes. Custa dólares (fal.ai): rascunho barato, aprovação dele, depois o final.
---

# Gaspar V2V — o cenário muda, o André fica igual

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
