# Fase 1 do plano Hermes → Jarvis — instruções para o agente de desenvolvimento

Você vai implementar a Fase 1 ("Mãos") do plano em `docs/plano-evolucao-hermes-jarvis.md`, seção 5 (Roadmap). A Fase 0 (fila de atenção, detectores, outbox com aprovação, duas rotinas agendadas) já está mergeada — PRs #153 a #156. Esta fase dá ao Hermes um jeito de enfileirar trabalho **autônomo** (que não precisa de decisão do dono) para a próxima sessão agendada do Claude executar sozinha.

São **cinco PRs**, cada um com seu arquivo de handoff. Só o 01 está detalhado por enquanto — os handoffs de 02 a 05 chegam um de cada vez, depois que o anterior estiver mergeado e verificado. Não comece um PR sem o handoff dele existir neste diretório.

| # | PR | Arquivo de handoff | Toca | Depende de |
|---|---|---|---|---|
| 1 | `feat(agent-requests): fila de trabalho autonomo e consolidacao de audio` | `01-agent-requests.md` | `functions/agent_requests.py` (novo), `functions/atencao_whatsapp.py`, `functions/tools/*` | PR #155 (detectores) |
| 2 | `feat(agent-runs): observabilidade das sessoes agendadas` | `02-agent-runs.md` (a escrever) | `functions/agent_runs.py` (novo), `functions/tools/*` | PR 1 desta fase |
| 3 | `feat(outbox): aprovacao por resposta no whatsapp proprio` | `03-whatsapp-proprio.md` (a escrever) | `functions/outbox_aprovacao.py`, `functions/whatsapp_ingest.py` | PR #156 (outbox) |
| 4 | `feat(github): webhook para diario da acao` | `04-webhook-github.md` (a escrever) | `functions/main.py` (nova Cloud Function HTTP) | Nenhuma desta fase |
| 5 | `feat(acoes): contexto_agente auto-mantido em acoes criticas` | `05-contexto-agente.md` (a escrever) | `functions/main.py`, `functions/tools/hermes_tools.py` | Nenhuma desta fase |

Os PRs 2 a 5 não dependem uns dos outros — podem ser feitos em qualquer ordem depois do 1, mas o 1 vem primeiro porque introduz `agent_requests`, que os outros podem vir a usar.

## Antes de qualquer coisa

1. Releia `docs/handoffs-fase0/00-leia-primeiro.md` — as regras globais de lá (convenção de tool nova, detectores determinísticos, flags desligadas por padrão, não tocar em `askCopilotoHermes`, não mandar mensagem a terceiro sem aprovação, documentar em `docs/okf/`) **continuam valendo integralmente** e não serão repetidas aqui.
2. Confira `git log --oneline -10` — o topo deve ter os commits dos PRs #153-#156. Se não tiver, pare e avise: significa que a Fase 0 não está completa na sua cópia.
3. **CRLF:** o mesmo aviso da Fase 0 vale em dobro aqui. Se `git diff --stat` mostrar centenas de linhas num arquivo que você tocou pouco, normalize para LF antes de comparar e de commitar. Confira sempre `git diff --cached --stat` (não só `git status`) imediatamente antes de cada commit.

## Regra nova desta fase: o que pode virar `agent_requests` e o que não pode

`agent_requests` é fila de trabalho **autônomo** — o Hermes enfileira, uma sessão agendada do Claude executa sozinha, sem perguntar nada ao dono antes. Isso só é seguro para o nível "Autônomo" da tabela do Eixo 3 (seção 3 do plano): registrar no diário, consolidar áudio, vincular com match determinístico, atualizar `data_prevista` com evidência, criar item na fila. **Nunca** é uma via para efeito em terceiro (mensagem, e-mail) — se um tipo de pedido futuro puder terminar em contato com alguém, o resultado do trabalho autônomo é sempre um rascunho no outbox (`criar_rascunho_whatsapp`/`criar_rascunho_email`), nunca um envio direto. Essa barreira do Eixo 3 não muda nesta fase, só ganha mais uma porta de entrada.

## Como testar

Os mesmos gates de sempre:

```bash
cd functions
python -m unittest discover -s . -p "test_*.py"

npm test
npm run build
```

## Commits e PR

Mesma convenção da Fase 0 — mensagens em português, corpo explica o porquê, descrição do PR com contexto/o que foi feito/como foi testado/o que ficou de fora.

## Critério de pronto do pacote (Fase 1 completa)

Um áudio de contato vinculado a ação ativa chega consolidado no diário da ação **sem o dono ter pedido**, com o item da fila de atenção correspondente já resolvido; `agent_runs` tem um registro por execução de cada rotina agendada com um resumo do que ela fez; o dono consegue aprovar um rascunho do outbox respondendo no próprio WhatsApp, não só pelo Telegram; um push/merge num repositório administrado por ele vira entrada no diário da ação certa; e `obter_acao(id)` devolve um resumo (`contexto_agente`) que um agente novo, em sessão zerada, consegue usar para continuar uma ação crítica sem mais nenhuma pergunta.
