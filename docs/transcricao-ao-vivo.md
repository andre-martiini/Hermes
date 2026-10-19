# Transcrição ao vivo para o Claude — handoff

Objetivo: o Claude, pelo conector MCP do Gaspar, lê a transcrição de uma reunião ou webinário **enquanto ela acontece**, aos poucos, sem o André colar texto.

## Onde a transcrição nasce

| Motor | Áudio | Falante | Onde fica |
|---|---|---|---|
| **Reuniões em Tempo Real** (web do Gaspar, `src/hooks/useMeetingRecordingEngine.ts`) | microfone ("Você") e áudio da tela/aba ("Reunião"), cada um num WebSocket do navegador direto ao Deepgram (nova-2, pt-BR) | só pelo canal | trechos em `transcricoes_ao_vivo` durante a reunião (PR 1); a reunião inteira em `reunioes` ao parar |
| **Live Ideas** (notebook, repositório `live-ideas`) | AssemblyAI ou Soniox | diarização ("Falante A") | `reunioes/<id>/eventos.jsonl` no notebook |

## PR 1 — gravação aos poucos (ferramenta de reuniões)

- `src/utils/transcricaoAoVivo.ts` (`SincronizadorTranscricao`): cada resultado final do Deepgram entra num buffer; a cada 10 s as falas pendentes viram um lote (falas seguidas do mesmo falante viram um trecho de até 1.500 caracteres) e vão à callable `transcricaoAoVivo`. Um lote por vez; se falhar, o mesmo lote (mesmo `lote_id` e `base_seq`) vai de novo no ciclo seguinte. Sem texto novo por 30 s, manda um sinal de vida. Ao parar: esvazia o buffer, `encerrar`, e depois de salvar a reunião, `vincular` (título gerado e id do doc em `reunioes`).
- `functions/transcricao_ao_vivo.py`: `iniciar` (idempotente; o id da sessão vem do navegador), `anexar` (transação: confere `base_seq == ultimo_seq`, grava `trechos/{seq:08d}` com seq contínuo e atualiza a sessão; o mesmo `lote_id` devolve `ja_gravado`), `encerrar` (idempotente; depois disso não entra texto novo) e `vincular`. Só o dono (`_require_internal_user`). Sem IA.
- `firestore.rules`: `transcricoes_ao_vivo` (e a subcoleção) fechada ao cliente; só o servidor toca.
- Atraso esperado entre a fala e a gravação: resultado final do Deepgram (1–3 s) + até 10 s do ciclo + a chamada (< 1 s quente) ≈ **até ~15 s**.
- Modelo dos documentos: `docs/okf/arquitetura/schema-firestore.md` (`transcricoes_ao_vivo`).

## PR 2 — tools de leitura (MCP)

Código em `functions/tools/transcricao_ao_vivo_tools.py`; somente leitura, sem IA, mesma autenticação das outras tools.

- `listar_transcricoes_ao_vivo(apenas_ativas=true, limite=10)`: `sessao_id`, `titulo`, `estado`, `iniciada_em` (horário de Brasília), `ultimo_seq`, `segundos_desde_ultimo_trecho`, `sem_sinal` (ao vivo sem lote nem sinal de vida há mais de 2 min), `total_caracteres`, `terceiros_presentes`, `reuniao_id`. Ativas = `ao_vivo` com sinal nos últimos 30 min (a aba fechada no meio sai da lista sozinha).
- `ler_transcricao_ao_vivo(sessao_id="mais_recente_ativa", apos_seq, ultimos_minutos, max_caracteres=12000)`: os trechos com `seq > apos_seq`, inteiros, até o teto (1.000–50.000; o primeiro trecho sempre vem). Devolve `proximo_seq` (passe como `apos_seq` na próxima), `ultimo_seq`, `truncado`, `estado`, `atraso_segundos` (desde o último trecho gravado), `sem_sinal` e uma `orientacao` dizendo quando chamar de novo. `ultimos_minutos` só vale sem `apos_seq`. Os trechos não mudam depois de gravados, então a mesma chamada devolve sempre o mesmo texto.
- Instrução do servidor MCP (`mcp_server.py`) e descrições das tools explicam o cursor; `ler_transcricao_ao_vivo` fica fora do canal de voz.
- Custo de uma leitura: 1 leitura da sessão + 1 por trecho devolvido (com `ultimos_minutos`, mais 1).

Uso típico pelo Claude: `listar_transcricoes_ao_vivo` → `ler_transcricao_ao_vivo(sessao_id)` → a cada ~30 s `ler_transcricao_ao_vivo(sessao_id, apos_seq=<proximo_seq>)` até `estado = encerrada`.

## PR 3 — `incluir_transcricao` no `liveideas_ler` (Live Ideas)

- Gaspar (`functions/tools/liveideas_tools.py`): `liveideas_ler(reuniao_id, incluir_transcricao=true, apos_seq=0, max_caracteres_transcricao=12000)` pede ao notebook `transcricao: {apos, max}` e devolve `transcricao: {trechos: [{seq, t, falante, texto}], proximo_seq, ultimo_seq, truncado, estado, orientacao}`. O teto (1.000–50.000) é reaplicado no Gaspar. Sem o parâmetro (padrão false) nada muda. Com processo, recusa sem chamar o notebook. Notebook ainda não atualizado: `transcricao.erro` pede o `atualizar-servidor.ps1`.
- Notebook (repositório `live-ideas`, PR andre-martiini/live-ideas#1): rota interna `/api/leitura/transcricao` lê `transcricao.txt` depois do cursor; `seq` = número da linha (o L<n> das evidências; linha em branco não vem, então pode haver salto); `estado` = `ao_vivo` se a reunião é a ativa e está em andamento. Cada fala entra no arquivo assim que o provedor (AssemblyAI/Soniox) fecha a frase, a cada ~6–10 s.
- Para valer: mesclar os dois PRs e rodar `atualizar-servidor.ps1` no notebook.

## Limites conhecidos

- Aba fechada no meio da reunião: a sessão fica `ao_vivo` sem sinal de vida. Quem lê usa o tempo desde a última atualização para perceber.
- O título começa como o do evento da agenda (ou "Reunião dd/mm hh:mm") e só vira o título gerado depois de parar.
- O link do vídeo (`url`) é aceito pela callable, mas a tela ainda não pergunta.
- Os trechos ficam guardados como a reunião em `reunioes` (sem prazo de expiração).

## Como testar ao vivo

1. Abrir Ferramentas › Reuniões em Tempo Real, gravar com o áudio de um vídeo do YouTube tocando.
2. Conferir no console do Firebase a sessão em `transcricoes_ao_vivo` com `ultimo_seq` subindo a cada ~10 s.
3. Parar: a sessão vira `encerrada` e, alguns segundos depois, ganha o título e o `reuniao_id`.
