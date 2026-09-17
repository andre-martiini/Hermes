# PR 3 — `feat(atencao): detectores promessa sem retorno e audio relevante`

**Pré-requisito:** PR 2 mergeado (coleção `atencao`, `chave_dedupe`, tools).

## Por quê

Dois casos reais de 03/09/2026 que o sistema poderia ter percebido sozinho:

- 14:24 o dono escreveu "Bom dia Guilherme, já estou vendo, ok?" e o retorno só saiu perto das 15h porque ele lembrou. Uma promessa feita em conversa não deixa rastro em lugar nenhum do Hermes.
- 13:50 chegaram dois áudios do Guilherme, contato vinculado a uma ação em andamento. A transcrição só aconteceu quando o dono pediu. O mesmo tinha acontecido com o áudio do Serviço Social de Piúma pela manhã.

Os dois detectores vivem em `functions/atencao_whatsapp.py` (novo), acionados por **trigger Firestore** em `whatsapp_messages/{id}` (on-create), cada um atrás da própria flag. Trigger e não cron, porque a latência importa: um áudio relevante deve virar item em segundos, e a promessa precisa registrar a hora exata em que foi feita.

## Detector A — `promessa_sem_retorno`

Flag: `system/settings.atencao.promessa_sem_retorno.enabled`. Parâmetro: `system/settings.atencao.promessa_sem_retorno.horas` (padrão `4`).

**Fase 1 — detectar a promessa (no trigger on-create):**

Mensagem com `from_me == true`, `message_type == "chat"`, chat **não** é grupo (`is_group == false`) — grupos ficam fora nesta versão — e `content` casa com um padrão de compromisso. Lista inicial, em `_PADROES_PROMESSA` (regex, case-insensitive, sem acento via normalização NFD como `utils/searchNormalization` faz no MEC-Sustentável — aqui em Python):

```
vou ver e te (retorno|falo|aviso)
(ja|já) estou vendo
te (retorno|aviso|falo) (ainda hoje|hoje|amanha|depois|mais tarde|em breve|assim que)
vou (verificar|checar|conferir|olhar) e (te )?(retorno|aviso|falo)
deixa comigo
pode deixar
```

Quando casa, gravar `promessas_abertas/{chat_id}_{wa_message_id}`: `{chat_id, chat_name, mensagem_id, texto, prometido_em: timestamp, vence_em: prometido_em + horas, estado: "aberta"}`. Se já existe promessa `aberta` no mesmo chat, **substitua** a mais antiga (uma promessa nova renova o compromisso; não acumule).

**Fase 2 — fechar ou vencer:**

- No mesmo trigger, para qualquer mensagem `from_me == true` em um chat com promessa `aberta`: se a mensagem **não** é ela própria uma promessa e tem mais de 40 caracteres, ou contém mídia/documento, marcar a promessa como `cumprida`. Mensagens curtas ("ok", "beleza", os `_DEFAULT_ENDINGS` de `inbox_pendentes.py`) não cumprem.
- Cron a cada 15 min (`vencer_promessas`, mesma flag): para promessas `aberta` com `vence_em <= agora`, criar item na fila: `origem="whatsapp"`, `tipo="promessa_sem_retorno"`, `prioridade="alta"`, `pessoa=chat_name`, `titulo="Você disse a {chat_name}: '{texto}' há {n}h e ainda não respondeu"`, `evidencia={chat_id, mensagem_ids:[mensagem_id]}`, `sugestao="Responder ou avisar que vai demorar"`, `chave_dedupe="promessa_sem_retorno:{chat_id}:{mensagem_id}"`. Marcar a promessa como `vencida`. Se a ação tiver `whatsapp_vinculos` com esse `chat_id`, preencher `acao_id`.

Uma promessa `vencida` cujo chat receba depois uma mensagem cumpridora deve **resolver o item** automaticamente (`estado="resolvido"`, `desfecho="respondeu em {hora}"`) — é o único caso em que um detector fecha item sem o dono. Registre o motivo em comentário.

## Detector B — `audio_relevante`

Flag: `system/settings.atencao.audio_relevante.enabled`. Parâmetro: `system/settings.atencao.audio_relevante.segundos_min` (padrão `20`).

No trigger on-create: mensagem `from_me == false`, `message_type in ("ptt", "audio")`. Relevante quando **qualquer** condição vale:

1. O `chat_id` aparece em `tarefas.whatsapp_vinculos` de alguma ação ativa (mesma varredura que `inbox_pendentes.py` faz na linha ~202 — extraia uma função compartilhada em vez de copiar).
2. O chat é individual e o contato tem `perfil_pessoas` vinculado (`linkWhatsappContacts` grava esse vínculo — confira o campo usado) com alguma ação ativa.

Duração: `whatsapp_messages.media` deve trazer a duração quando o worker captura mídia — confirme o nome do campo em `services/whatsapp-capture/index.js::captureMedia`. Se não houver duração gravada, **trate como relevante** (não silencie por falta de dado) e anote no PR que o worker deveria passar a gravar `media.duration_seconds`.

Item: `origem="whatsapp"`, `tipo="audio_relevante"`, `prioridade="media"` (ou `alta` se a ação vinculada for crítica), `acao_id` da ação, `pessoa=author_name`, `titulo="Áudio de {author_name} ({n}s) na conversa vinculada a '{titulo da ação}'"`, `evidencia={chat_id, mensagem_ids:[id]}`, `sugestao="Consolidar com consolidar_whatsapp e registrar no diário da ação"`, `chave_dedupe="audio_relevante:{chat_id}:{wa_message_id}"`.

Vários áudios em sequência (mesmo chat, < 10 min entre eles) devem virar **um** item, com todos os ids em `evidencia.mensagem_ids`: use como `chave_dedupe` a do primeiro áudio da sequência e faça `merge` nos seguintes.

**Este PR não transcreve nada.** Transcrever custa dinheiro e é decisão do consumidor da fila (o Claude, via `consolidar_whatsapp`). Deixe explícito no docstring.

## Testes

`functions/test_atencao_whatsapp.py` (novo), com a lógica pura separada do Firestore como no PR 2:

- Promessa: cada padrão da lista casa; frase parecida sem compromisso não casa ("estou vendo o jogo"); mensagem curta não cumpre; mensagem longa cumpre; promessa nova substitui antiga; vencimento gera item com a `chave_dedupe` esperada; resposta depois do vencimento resolve o item.
- Áudio: áudio de chat vinculado gera item; áudio de chat não vinculado não gera; três áudios em 5 min viram um item com três ids; áudio `from_me` não gera.

Gate completo: `cd functions && python -m unittest discover -s . -p "test_*.py"`.

## Firestore

Coleção nova `promessas_abertas` (regras: só Admin SDK). Índice em `promessas_abertas` por `estado ASC, vence_em ASC`.

## Fora de escopo

Grupos; promessas feitas por e-mail; detecção por LLM de compromissos fora dos padrões (fica para quando houver dado de quantas promessas os padrões perdem — a retro semanal do plano é quem vai medir isso).

## Docs

`schema-firestore.md` (`promessas_abertas`, novos `tipo` da fila), `cloud-functions.md` (as duas funções), `integracoes/whatsapp.md` (o que o trigger faz com cada mensagem), `log.md`.
