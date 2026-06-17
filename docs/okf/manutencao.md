---
type: policy
title: Como manter este bundle atualizado
description: Regras de quando e como atualizar os documentos OKF do Hermes — especialmente os de arquitetura — para que não fiquem obsoletos.
tags: [hermes, okf, manutencao, governanca]
timestamp: 2026-06-17T00:00:00Z
---

# Como manter este bundle atualizado

Um bundle OKF só tem valor enquanto reflete a realidade do sistema. Documentação desatualizada é pior do que nenhuma documentação, porque engana com confiança — tanto um desenvolvedor humano quanto um agente de IA vão confiar no que está escrito aqui em vez de checar o código. Esta página define quando e como atualizar cada categoria.

## Categorias e sua volatilidade

| Categoria | Muda quando | Quem deve atualizar |
|---|---|---|
| [Arquitetura](/docs/okf/arquitetura/index.md) | Toda vez que a estrutura do sistema muda (ver lista abaixo) | Quem fez a mudança — humano ou agente de IA |
| [Operações](/docs/okf/operacoes/index.md), [Integrações](/docs/okf/integracoes/index.md), [Guias](/docs/okf/guias/index.md), [UI](/docs/okf/ui/index.md) | Raramente — só quando o procedimento documentado deixa de funcionar como descrito | Quem notar a divergência |
| [Copiloto](/docs/okf/copiloto/index.md) | Quando há mudança de arquitetura no Copiloto (RAG, gating, ferramentas) | Quem fez a mudança |

## Gatilhos obrigatórios para `arquitetura/`

Se você (humano ou agente de IA) fizer qualquer uma das mudanças abaixo, **a mesma tarefa inclui atualizar o documento correspondente** — não é um follow-up opcional:

- **Nova coleção do Firestore, ou novo campo relevante em coleção existente** → atualizar [`schema-firestore.md`](/docs/okf/arquitetura/schema-firestore.md).
- **Nova Cloud Function, função removida, ou mudança de tipo de trigger** (ex.: callable → scheduled) → atualizar [`cloud-functions.md`](/docs/okf/arquitetura/cloud-functions.md).
- **Mudança de stack de frontend, novo padrão de pasta, adoção de state management global, mudança no padrão de services** → atualizar [`convencoes-frontend.md`](/docs/okf/arquitetura/convencoes-frontend.md).

Mudanças que NÃO exigem atualização: ajustes de UI sem impacto estrutural, correção de bugs, refatoração interna que não muda a interface pública (schema/trigger/convenção).

## Como atualizar

1. Edite o(s) documento(s) afetado(s) diretamente — não crie um documento novo para "complementar" um já existente, edite o existente.
2. Atualize o campo `timestamp` do frontmatter para a data da mudança.
3. Adicione uma linha em [`log.md`](/docs/okf/log.md) descrevendo o que mudou e por quê (1 linha basta).
4. Se a mudança tornar um documento de outra categoria obsoleto ou impreciso, corrija-o na mesma tarefa.

## O que não pertence a este bundle

- **Handoffs de tarefa pontual** (ex.: "o que falta fazer depois do commit X"): vivem na descrição do commit/PR. Uma vez mergeados, perdem relevância como documento de referência — não devem ser adicionados aqui, e se existirem devem ser removidos (ver `log.md` para um exemplo já feito).
- **Planos de implementação já executados**: mesma lógica — o código é a fonte de verdade depois que o plano é executado.
- **Conhecimento operacional do usuário** (procedimentos, regras de negócio, fatos sobre tarefas): isso continua no knowledge graph em Firestore (`knowledge_nodes`/`knowledge_edges`), não neste bundle — ver nota em [`docs/okf/index.md`](/docs/okf/index.md).

## Para agentes de IA externos

Se você é um agente de IA chegando a este repositório pela primeira vez para desenvolver alguma funcionalidade: leia [`docs/okf/index.md`](/docs/okf/index.md) e a categoria [`arquitetura/`](/docs/okf/arquitetura/index.md) antes de explorar o código-fonte — isso economiza várias rodadas de busca. Depois de fazer uma mudança estrutural, aplique os gatilhos desta página antes de considerar a tarefa concluída.
