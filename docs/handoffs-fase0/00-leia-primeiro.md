# Fase 0 do plano Hermes → Jarvis — instruções para o agente de desenvolvimento

Você vai implementar a Fase 0 do plano em `docs/plano-evolucao-hermes-jarvis.md`. São **quatro PRs independentes**, nesta ordem. Não comece o seguinte antes de o anterior estar mergeado — o 03 depende de coleção e tools criadas no 02, e o 04 reaproveita padrões que o 02 estabelece.

| # | PR | Arquivo de handoff | Toca |
|---|---|---|---|
| 1 | `fix(whatsapp): last_activity_ts atualizado a cada mensagem capturada` | `01-fix-ultima-atividade.md` | `services/whatsapp-capture/index.js` |
| 2 | `feat(atencao): fila de atencao, tools e detector aguardando_terceiro vencido` | `02-fila-de-atencao.md` | `functions/atencao.py` (novo), `functions/tools/*`, `functions/morning_summary.py` |
| 3 | `feat(atencao): detectores promessa sem retorno e audio relevante` | `03-detectores-whatsapp.md` | `functions/atencao.py`, `functions/atencao_whatsapp.py` (novo) |
| 4 | `feat(outbox): rascunhos com aprovacao em um toque pelo Telegram` | `04-outbox-aprovacao.md` | `functions/tools/*`, `functions/hermes_core_logic.py` |

## Antes de qualquer coisa

1. Leia `docs/okf/index.md`, `docs/okf/copiloto/mcp-servidor.md` (seção "Adicionar uma tool nova") e `docs/okf/arquitetura/cloud-functions.md`. Eles descrevem as convenções que este pacote assume.
2. Confira o estado do repositório: `git log --oneline -20`, `git status`, branches abertas. A working tree em `main` costuma ter muitos arquivos com diferença só de CRLF — **não commite nada que você não alterou de propósito**. Se `git diff --stat` mostrar centenas de linhas num arquivo que você mexeu pouco, normalize as duas versões para LF antes de comparar (`git show HEAD:<arquivo> | sed 's/\r$//'` vs. `sed 's/\r$//' <arquivo>`).
3. Trabalhe em branch própria a partir de `main` (`feat/atencao-...` ou `fix/whatsapp-...`). Um PR por handoff.

## Regras globais (valem para os quatro PRs)

- **Não crie orquestrador nem catálogo novo.** Toda tool nova entra pelo caminho existente: handler em `functions/tools/hermes_tools.py::_HANDLERS`, descrição em `functions/tools/registry.py::_CATALOG`, schema em `functions/tools/schemas/<nome>.json`. Se grava, entra em `registry._NEEDS_CONFIRMATION`. `functions/test_hermes_tools.py` falha se faltar uma das três.
- **Detectores são determinísticos.** Nenhuma chamada a LLM na detecção. Regex, comparação de datas e leitura de Firestore. O raciocínio fica com o Claude, que consome a fila.
- **Toda automação nova nasce atrás de flag desligada:** `system/settings.atencao.<nome>.enabled` (padrão `false`). O documento `system/settings` só é acessível pelo Admin SDK — exponha o toggle em `getAutomationSettings`/`updateAutomationSettings` (`functions/main.py`, ~linha 13550) se o PR criar uma flag nova.
- **Não toque em `askCopilotoHermes`** nem em `functions/main.py` além do estritamente indicado em cada handoff.
- **Não mande mensagem a terceiros.** Nenhum PR deste pacote envia WhatsApp ou e-mail para alguém que não seja o dono. O 04 cria rascunhos que só saem depois de aprovação humana.
- **Documente em `docs/okf/`** o que mudar de arquitetura (nova coleção, nova Cloud Function, nova tool) — atualize `docs/okf/arquitetura/cloud-functions.md` e `docs/okf/arquitetura/schema-firestore.md`, e registre em `docs/okf/log.md`. Leia `docs/okf/manutencao.md` antes.

## Como testar (os mesmos gates do CI em `.github/workflows/pr.yml`)

```bash
# Functions Python
cd functions
python -m unittest discover -s . -p "test_*.py"

# Frontend (só se tocar em src/ ou na raiz)
npm test
npm run build
```

Um PR que quebra qualquer um desses não é aberto.

## Commits e PR

- Mensagens de commit em português, no padrão do repositório: `tipo(escopo): descrição no infinitivo ou substantivo`. Exemplos reais do log: `feat(investimentos): criar acao no Hermes automaticamente ...`, `fix(mcp): três escritas que respondiam sem gravar`.
- Corpo do commit explica **por quê**, não o quê — o diff já diz o quê. O repositório tem essa cultura (leia os comentários em `registry.py` e `mcp_signals.py`).
- Descrição do PR: contexto em 3 linhas, o que foi feito, como foi testado, o que ficou de fora e por quê.

## Critério de pronto do pacote

A Fase 0 está pronta quando, com as flags ligadas no Firestore: `obter_estado_atual` devolve uma chave `fila_atencao` com itens reais; um passo de `plano_acao` em `aguardando_terceiro` com `data_prevista` passada gera item automaticamente; uma mensagem do dono do tipo "vou ver e te retorno" sem resposta posterior gera item após o prazo configurado; um áudio de contato vinculado a ação ativa gera item com sugestão de consolidação; um rascunho em `whatsapp_outbox` com `status: aguardando_aprovacao` só é enviado depois do toque em "Enviar" no Telegram — e `listar_conversas_whatsapp` mostra `ultima_atividade` correta em tempo quase real.
