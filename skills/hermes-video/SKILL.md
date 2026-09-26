---
name: hermes-video
description: Produz um vídeo curto (15 s a 2 min, 16:9 ou 9:16) pelo Hermes Vídeo — roteiro, storyboard e renderização no Veo com narração, entregue como MP4 no Drive. Use quando o André pedir um vídeo, animação, clipe explicativo ou "um vídeo de X segundos sobre Y", ou quando quiser ajustar, refazer uma cena, acompanhar ou cancelar um vídeo do Hermes. Conduz duas aprovações (roteiro e storyboard) antes de qualquer gasto relevante e usa as tools video_* do conector Hermes.
---

# Hermes Vídeo

Você escreve e conduz; o Hermes executa o que custa dinheiro, guarda os arquivos e controla o gasto. O André só conversa com você. Ele aprova duas vezes antes do passo caro: o **roteiro** (custo zero) e o **storyboard** (centavos). Renderizar sempre pede o "sim" dele com o custo na tela.

## Fluxo

1. **Pedido.** Tema, público, duração e formato. Se faltar algo essencial, faça **uma** pergunta e siga com os padrões: 16:9, 60 s, voz Kore em tom calmo e didático, modo padrão (Veo 3.1 Lite). Pergunte a ação do Hermes à qual o vídeo pertence (vai para o diário dela); se não houver, siga sem.
2. **Roteiro — aprovação 1 (custo zero).** Mostre uma tabela: cena, narração, o que aparece na tela, duração prevista. Junto: a bíblia visual (estilo, paleta, personagens, o que evitar) e a estimativa. Ajuste até ele aprovar em linguagem livre.
3. **Criar o projeto.** `video_criar_projeto` com o roteiro aprovado. Se vier `invalido`, corrija o que os erros pedem (ex.: dividir uma cena longa) e mostre o que mudou.
4. **Prévia (~US$ 0,01 por narração + US$ 0,04 por quadro).** `video_gerar_previa` → roda como job: chame `consultar_job` com o `job_id` até terminar (leva de 1 a 4 min). O resultado traz a folha de contato (PNG) e a narração completa (MP3) no Drive, a duração real de cada cena, cenas a dividir, falhas de quadro e a estimativa refeita.
5. **Storyboard — aprovação 2.** Mostre a folha de contato (abra o arquivo do Drive pelo `drive_id` para vê-la e descreva o que há em cada quadro), o link do MP3 e a estimativa com as durações reais. Pedidos de mudança → `video_ajustar` (só o que mudou é refeito) e mostre de novo. Só avance com `renderizavel: true` e sem `falhas`.
6. **Renderizar (o passo caro).** `video_renderizar` devolve uma **prévia com o custo máximo**, o gasto do mês e o teto mensal, e um `confirmation_id`. Mostre esses números ao André e **só** chame `confirmar_acao(confirmation_id)` depois do "sim" explícito dele. O worker leva ~1 min por cena; acompanhe com `video_status` se ele pedir. O Hermes avisa no Telegram e anexa o MP4 à ação quando terminar.
7. **Ajuste fino.** "Refaz a cena 3 com a câmera mais aberta" → `video_refazer_cena(projeto_id, ordem=3, instrucao=...)`, que também pede confirmação com o custo. Avise que refazer só uma cena pode deixar um pequeno salto na emenda com a seguinte; `refazer_seguintes=true` refaz até o fim (emenda perfeita, custo maior).

## Escrevendo o roteiro

- **Ritmo da narração: ~2 palavras por segundo** (medido no TTS real). Cada cena vira um clipe de 4, 6 ou 8 s; o máximo é **~15 palavras por cena** (8 s). Mais que isso, divida a cena. O vídeo inteiro fica entre 15 s e 120 s.
- **Uma ideia por cena**, frases curtas, sem siglas não explicadas na primeira vez. Cena sem narração é permitida (vira 4 s de imagem).
- **Descrição visual = um único instante**: o que se vê no fim daquela cena. Personagem, ação, lugar, enquadramento. Nada de "e depois", nada de duas situações no mesmo quadro.
- **Bíblia visual**, repetida em toda cena pelo Hermes:
  - *Estilo*: técnica e acabamento (ex.: "ilustração flat 2D, traço limpo, iluminação difusa"). Estilos ilustrados mantêm a personagem mais estável que fotorrealismo.
  - *Paleta*: 2 a 4 cores.
  - *Personagens*: aparência fixa de cada um (idade aparente, cabelo, roupa, acessório marcante). A personagem só aparece nas cenas que a mencionam.
  - *Evitar*: sempre "texto na imagem, logotipos, rostos de pessoas reais".
- **Prompt de movimento** (opcional, `prompt_video`): câmera ("câmera se aproxima devagar", "plano fixo"), ação ("ela fecha a pasta e se levanta") e ritmo ("movimento suave"). Sem cortes nem trocas de cenário dentro de uma cena.

## Limites e segurança

- Não gere pessoas reais identificáveis (família, colegas, autoridades), crianças, marcas ou logotipos. O filtro do Veo barra, e uma cena barrada duas vezes fica `bloqueado` até a descrição mudar.
- Uso de imagem de pessoa real está fora da v1.
- Tetos (em `config/video_precos`): US$ 1 por prévia, US$ 3 em prévias por projeto, teto por projeto de 1,5× a estimativa (máx. US$ 20) e **US$ 30 por mês**. Quando uma tool recusa por teto, explique qual e ofereça encurtar o vídeo ou usar o modo padrão.
- Custo de referência: 1 min no modo padrão ≈ US$ 4–5; no modo final (Fast) ≈ US$ 9–13.

## Estados e erros

`roteiro` → `previa_gerando` → `aguardando_storyboard` → `renderizando` → `montando` → `concluido` (ou `erro`/`cancelado`).

- **`erro` na prévia**: gere a prévia de novo; o que já saiu não é pago outra vez.
- **`erro` na renderização**: `video_renderizar` retoma (nova confirmação); clipes prontos não são pagos de novo.
- **Renderizando parado há muito tempo** (sem avanço no `video_status` por mais de 15 min): `video_renderizar` retoma o worker.
- **"O projeto mudou desde a prévia que o usuário aprovou"**: peça a confirmação de novo com a prévia atual.
- **"Worker desatualizado"**: o André precisa rodar `deploy_video_worker.bat`.
- **Cancelar** (`video_cancelar`) é final e perde o trabalho pago; confirme com o André antes, mesmo a tool não exigindo.

## Tools

| Tool | Quando | Custo |
| --- | --- | --- |
| `video_criar_projeto` | Roteiro aprovado | Zero |
| `video_gerar_previa` (job) | Depois de criar, ou para regerar | Centavos, com teto |
| `video_ajustar` (job) | Mudanças no storyboard | Só o que mudou |
| `video_status` | Acompanhar | Zero |
| `video_renderizar` | Storyboard aprovado; retomar | Pago — confirmação obrigatória |
| `video_refazer_cena` | Vídeo pronto, ajustar uma cena | Pago — confirmação obrigatória |
| `video_cancelar` | Desistir | Zero (final) |
