# Proposta: wrapper de I/O de `Mandato` e taxonomia de `classes_conteudo_permitidas`

Documento de proposta, não de execução — não é uma sub-entrega de código, não altera `docs/autonomia/execucao.md`. Responde às duas perguntas deixadas em aberto ao final da sub-entrega 16/N (`docs/autonomia/execucao.md`): que mandatos existem hoje na prática, e que categorias de conteúdo o Hermes pode usar para falar com terceiros sem confirmação humana por instância. André pediu uma proposta ("me faça uma proposta para estas duas questões"), não uma decisão autônoma — este documento existe para ele revisar e decidir, não para eu implementar direto.

## A resposta curta

As duas perguntas já têm resposta em produção — só não está modelada como `autonomy.contracts.Mandato`. `system/mcp_access.tipos_promovidos` (`functions/outbox_aprovacao.py`, `functions/promocao_autonomia.py`) é, na prática, exatamente um mandato por classe de conteúdo: um `tipo` de mensagem só entra nessa lista depois que `tipos_elegiveis_para_promocao()` mede volume real e taxa de aprovação sem edição no histórico de `whatsapp_outbox`, propõe a promoção, e o André decide explicitamente — aceitar, adiar ou nunca — via `decidir_promocao_autonomia()`. É um mandato data-driven e já supervisionado por humano, rodando hoje.

Proposta central: **não inventar uma taxonomia nova nem um formato de mandato novo. Ligar o `Mandato` de `autonomy/contracts.py` a este mecanismo já existente**, em vez de pedir ao André uma lista de categorias do zero ou um cadastro manual de mandatos que ele teria que manter à parte da vida real do sistema.

## Evidência levantada

- `functions/tools/schemas/criar_rascunho_whatsapp.json`: `tipo` é texto livre, rotulado pelo próprio Claude ao criar o rascunho ("rótulo curto e estável... usado para métricas de autonomia"), com exemplos como `confirmacao_reuniao`, `retorno_promessa`, `cobranca_terceiro`.
- `functions/promocao_autonomia.py::tipos_elegiveis_para_promocao()`: varre o histórico real de `whatsapp_outbox`, agrupa por `tipo`, e só considera candidato um `tipo` com amostra mínima e taxa de aprovação-sem-edição acima de um limiar — ou seja, a "categoria" só vira candidata a autonomia depois de um histórico real de o André aprovar sem mexer.
- `functions/promocao_autonomia.py::decidir_promocao_autonomia()`: o André decide por tipo — `aceitar` grava em `system/mcp_access.tipos_promovidos` (transacional); `nunca`/`adiar` não gravam. Já existe revogação implícita: remover o tipo dessa lista (não há hoje uma tool para isso, mas o dado é de fácil edição).
- `functions/outbox_aprovacao.py::_tipos_promovidos()` + `criar_rascunho()`: um rascunho cujo `tipo` está na lista promovida vira `STATUS_AGUARDANDO_JANELA` (envia sozinho após a janela de cancelamento, sem toque humano); os demais exigem aprovação manual no Telegram.
- `functions/outbox_aprovacao.py::liberar_rascunhos_promovidos()` — a função que a sub-entrega 15/N religou ao interruptor global de `EstadoAutonomia` — é exatamente o consumidor final desse mecanismo: dispara o envio automático quando a janela passa.

Ou seja, o sistema já teve, de forma independente do plano de autonomia (P02), que responder "quais mandatos existem" e "quais categorias" — e respondeu com um mecanismo funcional, testado, e já usado. A pergunta em aberto não é "quais são as categorias", é "como conectar essa resposta já existente ao motor novo (`autonomy/policy.py`)".

## Proposta de mapeamento — `Mandato` a partir de `tipos_promovidos`

Para cada `tipo` em `system/mcp_access.tipos_promovidos`, um wrapper de I/O novo (`autonomy/mandatos_io.py`, ainda não escrito) construiria:

| Campo do `Mandato` | Valor proposto | Origem |
|---|---|---|
| `mandato_id` | `f"tipo_promovido:{tipo}"` | derivado |
| `finalidade` | `f"envio_promovido:{tipo}"` (identificador estável, não uma frase livre) | derivado |
| `classes_conteudo_permitidas` | `(tipo,)` — só esse tipo | `system/mcp_access.tipos_promovidos` |
| `destinatarios_recursos` | `("*",)` — ver decisão pendente 1, abaixo | proposto (preserva o comportamento atual) |
| `limite_por_janela` / `janela_dias` | não populado (`None`) — sem limite adicional além do que já existe hoje | proposto (preserva o comportamento atual) |
| `orcamento_maximo` | não populado (`None`) — tipos promovidos hoje não têm dimensão financeira conhecida | proposto |
| `horario_permitido_*` | não populado — sem restrição de horário hoje | proposto |
| `valido_ate` | **decisão pendente 2, abaixo** — `mandato_cobre()` falha fechado sem isto | precisa de decisão |
| `origem_autorizacao` | referência ao aceite em `decidir_promocao_autonomia` (tipo + data, se disponível) | `promocoes_autonomia_sugeridas` |
| `forma_revogacao` | "remover `tipo` de `system/mcp_access.tipos_promovidos`" | descritivo |

No lado do pedido (`PolicyRequest`), quem monta a chamada para um envio de tipo promovido precisa passar `sensibilidade=tipo` (não `missao`) — é isso que `mandato_cobre()` compara contra `classes_conteudo_permitidas` — e `missao=f"envio_promovido:{tipo}"`, batendo com `finalidade`. As duas comparações do motor (finalidade/missão E classe de conteúdo) continuam ativas; elas só passam a bater porque os dois lados usam o mesmo identificador estável, derivado do mesmo `tipo`, em vez de duas strings pensadas por pessoas/momentos diferentes.

## Duas decisões que ainda são do André, não minhas

Diferente das três decisões da sub-entrega 15/N, estas duas não têm uma resposta "óbvia" só de ler o código — são sobre o que ele quer que o sistema faça de verdade com terceiros reais.

**1. Escopo de destinatário (`destinatarios_recursos`).** Hoje, um tipo promovido pode enviar a QUALQUER destinatário reconhecido — não há restrição por pessoa/contato. Proposta acima (`"*"`) preserva exatamente esse comportamento. Alternativa: `Mandato` já suporta lista fechada de destinatários (`_destino_coberto`, com suporte a domínio `@empresa.com`) — se o André quiser, por exemplo, que `cobranca_terceiro` só possa ir para contatos de um determinado grupo, isso já é possível estruturalmente, só precisa de uma fonte de dados (provavelmente um campo novo por tipo, não coberto por `tipos_promovidos` hoje). Recomendo começar com `"*"` (zero mudança de comportamento) e revisitar por tipo específico se algum caso concreto pedir.

**2. Validade (`valido_ate`).** `mandato_cobre()` foi deliberadamente desenhado (correção do Codex, PR #191) para NUNCA cobrir um mandato sem validade resolvida — sem isto, todo tipo promovido ficaria estruturalmente descoberto e o wrapper não teria efeito nenhum. Três caminhos, nenhum tecnicamente errado:
   - (a) Janela rolante automática (ex.: 30/60/90 dias a partir de agora, recalculada a cada leitura) — nunca expira de fato enquanto o tipo continuar em `tipos_promovidos`, mas respeita a forma como o campo foi desenhado.
   - (b) Perguntar "até quando?" no próprio fluxo de `decidir_promocao_autonomia` quando o André aceita uma promoção — mais fiel ao espírito da seção 5.3 do plano ("validade" como condição mínima real, não sintética), mas muda a UX de um fluxo que já funciona hoje sem essa pergunta.
   - (c) Revalidação periódica: promoção vale por N dias e "renova" sozinha só se a taxa de aprovação continuar alta (reaproveitando a mesma métrica de `tipos_elegiveis_para_promocao`) — mais trabalho de engenharia, mais alinhado com "autonomia crescente, mas nunca definitiva sem revisão".

Minha recomendação, se ele quiser uma só: (a) para não mudar a UX de um fluxo já testado em produção, com revisão de (c) como evolução natural mais tarde — mas esta é uma escolha dele, não uma correção técnica objetiva como as da sub-entrega 15/N.

## O que NÃO está nesta proposta

- Taxonomia nova de categorias — deliberadamente descartada; a proposta é usar o vocabulário que já existe (`tipo`), não inventar um enum fixo à parte.
- Conectar `outbox_aprovacao.py::criar_rascunho.tipo` a `Mandato.classes_conteudo_permitidas` na validação de ENTRADA (isso já está coberto — `Mandato.__post_init__` já rejeita `"outro"`/rótulo vazio desde a sub-entrega 15/N; o que falta é o lado de LEITURA, que é o assunto deste documento).
- Ligar `decisao_piso()` completo a `liberar_rascunhos_promovidos()`/`propor_reagendamento_semanal()` — é o passo seguinte, natural depois que o wrapper acima existir, mas fora do escopo desta proposta.

## Se aprovado, o que eu implementaria a seguir

Uma sub-entrega técnica (P02, número seguinte) que: (1) escreve `autonomy/mandatos_io.py` com a função de resolução acima, testada isoladamente; (2) religa `liberar_rascunhos_promovidos()` para consultar esse wrapper e chamar `decisao_piso()` de verdade (não só o interruptor global de `EstadoAutonomia`, como a sub-entrega 15/N fez); (3) suíte completa + revisão adversarial + PR, no mesmo padrão das sub-entregas anteriores. Só inicio isso depois de resposta do André às duas decisões acima — o resto é engenharia direta a partir daí.
