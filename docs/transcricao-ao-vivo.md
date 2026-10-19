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

## Limites conhecidos

- Aba fechada no meio da reunião: a sessão fica `ao_vivo` sem sinal de vida. Quem lê usa o tempo desde a última atualização para perceber.
- O título começa como o do evento da agenda (ou "Reunião dd/mm hh:mm") e só vira o título gerado depois de parar.
- O link do vídeo (`url`) é aceito pela callable, mas a tela ainda não pergunta.
- Os trechos ficam guardados como a reunião em `reunioes` (sem prazo de expiração).

## Como testar ao vivo

1. Abrir Ferramentas › Reuniões em Tempo Real, gravar com o áudio de um vídeo do YouTube tocando.
2. Conferir no console do Firebase a sessão em `transcricoes_ao_vivo` com `ultimo_seq` subindo a cada ~10 s.
3. Parar: a sessão vira `encerrada` e, alguns segundos depois, ganha o título e o `reuniao_id`.
