# Fluxo "Claude First" no Argos DevFlow — da demanda ao código (caso real DEV-2026-0002)

Este documento revisa o fluxo ponta a ponta que montamos nesta sessão para o conector Claude↔Argos DevFlow, usando como estudo de caso real a demanda `DEV-2026-0002` (atualizar o modelo Gemini Flash de 3.7 para 3.8 no `gestao-sigex`). Todos os IDs, commits, PRs e horários abaixo são os reais desta execução.

## O princípio do fluxo

A ideia central do "Claude First" é inverter quem inicia o trabalho: em vez de o André abrir uma demanda e esperar alguém (humano ou IA) puxá-la, o Claude identifica a necessidade, propõe o plano, e — uma vez aprovado — conduz a demanda sozinho até o código pronto para revisão, parando apenas nos pontos em que uma decisão humana real é exigida. Dois portões existem por desenho no `devflow.ts`: aprovar o plano (quando a classificação de risco exige) e autorizar o enfileiramento da execução. Todo o resto — criar a demanda, publicar a Issue no GitHub, avançar o estado, aplicar o código, abrir o PR — é bookkeeping que o Claude faz livremente, sem pedir permissão a cada passo.

Como o Claude não tem (nem pediu) credencial de push/merge em nenhum dos dois computadores usados nesta sessão, toda escrita em repositório remoto passa por um "Dev" externo credenciado (Antigravity, Codex ou similar), acionado por um prompt de handoff redigido pelo Claude. E desde a mudança de procedimento combinada nesta sessão, quem revisa o PR antes do merge é o próprio Claude — o André mescla direto com base nesse veredito, sem reler o diff manualmente no Antigravity como segunda camada.

## Passo a passo real

**1. Identificação e abertura da demanda (05/09, 22:54).** A necessidade partiu de um pedido direto do André: atualizar a opção "Flash" do assistente de IA do SIGEX para `gemini-3.8-flash`. A demanda foi classificada como `critical` (risco/complexidade) pelo classificador do DevFlow — o que automaticamente exige aprovação humana do plano — e a Issue correspondente foi publicada em `andre-martiini/gestao-sigex#1`.

**2. Proposta do plano (06/09, 08:50) — `argos_propor_plano`, sem portão.** O plano descreveu o escopo exato: alterar o `id` da entrada "Flash" em `MODELOS_GEMINI`, em `lib/gemini.ts`, de `gemini-3.7-flash` para `gemini-3.8-flash`, e acrescentar `'gemini-3.7-flash': 'gemini-3.8-flash'` a `MODELOS_LEGADOS`, para que configurações já salvas migrem sem quebrar. Escopo explicitamente fora: a opção Flash-Lite e a lógica de seleção de modelo pelo usuário.

**3. Aprovação humana do plano (06/09, 08:50–08:54) — primeiro portão.** Pedido de autorização via Telegram/Hermes (`solicitar_autorizacao_argos`, tipo `approve-plan`, solicitação `XTkVIvIA8RHtR8Q69RGm`). Só depois de `consultar_autorizacao_argos` confirmar status `aprovado` — nunca a partir de uma resposta ambígua no chat — o Claude chamou `consumir_autorizacao_argos` e então `argos_aprovar_plano`.

**4. A lacuna descoberta: não havia como avançar `plan-approved` → `ready-for-execution`.** Ao tentar continuar o teste de ponta a ponta, ficou claro que essa transição só existia via label manual no GitHub ou direto no console — nenhuma tool do conector cobria esse passo. O André pediu que isso ficasse automático. Isso levou a duas rodadas de desenvolvimento no `argos-gestor-sistemas`, ambas seguindo o mesmo padrão: Claude implementa e testa localmente, um Dev externo dá push e abre o PR, o Claude revisa (incluindo a revisão automática do bot Codex) e o André mescla, e por fim o Claude cria o lançamento manual no Firebase App Hosting (este repositório não tem CI/CD):

- **PR #8** (`b9aa8fa`, build `build-2026-09-06-000`) — correção de um bug pré-existente e não relacionado: a busca de Issues do GitHub passou a exigir o qualificador `is:issue`, sem o qual respondia 422, quebrando `findGithubIssueByMarker`. Encontrado ao testar a própria DEV-2026-0002.
- **PR #9** (`a98ea56`, build `build-2026-09-06-001`) — a nova operação `advanceToReadyForExecution`, exposta como a tool MCP `argos_marcar_pronto_para_execucao` e a rota `POST /systems/:id/demands/:demandId/ready-for-execution`. A revisão automática do Codex encontrou um bug real na primeira versão: o label do GitHub era trocado para "pronto para execução" *antes* de a transação no Firestore confirmar sucesso: se a transação falhasse (por exemplo, outra chamada bloqueando a demanda nesse intervalo), o label já estaria errado, e o webhook do GitHub poderia sincronizá-lo de volta, desfazendo silenciosamente a decisão concorrente. Corrigido reordenando para só tocar o GitHub depois de `applied === true`:

```ts
export async function advanceToReadyForExecution(deps: ClaudeConnectorDependencies, input: { systemId: string; demandId: string; notes?: string }) {
  const systemId = normalizeSystemId(input.systemId); const demandId = String(input.demandId || '').trim();
  assertAllowedSystem(deps, systemId);
  if (!deps.githubToken) throw new ClaudeConnectorError(503, 'Integração GitHub não configurada no servidor.');
  try {
    const demandRef = deps.db.collection('devflow_demands').doc(demandId); const demandSnap = await demandRef.get();
    if (!demandSnap.exists) throw new ClaudeConnectorError(404, 'Demanda não encontrada.');
    const demand = demandSnap.data() as DevFlowDemand;
    if (demand.system_id !== systemId) throw new ClaudeConnectorError(404, 'Demanda não encontrada.');
    const nextState: DevFlowDemandState = 'ready-for-execution';
    if (!isValidDevFlowTransition(demand.state, nextState)) throw new ClaudeConnectorError(409, `Transição inválida: ${demand.state} → ${nextState}.`);
    if (demand.classification?.requiresHumanPlanApproval) {
      const approvalsSnapshot = await deps.db.collection('devflow_approvals').where('demand_id', '==', demandId).get();
      const hasApprovedPlan = approvalsSnapshot.docs.some(doc => { const approval = doc.data() as DevFlowApproval; return approval.type === 'plan' && approval.status === 'approved'; });
      if (!hasApprovedPlan) throw new ClaudeConnectorError(409, 'A aprovação humana do plano é obrigatória antes de marcar como pronta para execução.');
    }
    const now = new Date().toISOString();
    const updatedDemand: DevFlowDemand = { ...demand, state: nextState, updated_at: now, github_synced_at: now };
    let applied = false;
    await deps.db.runTransaction(async transaction => {
      const freshSnap = await transaction.get(demandRef);
      if ((freshSnap.data() as DevFlowDemand | undefined)?.state !== demand.state) return;
      transaction.set(demandRef, updatedDemand, { merge: true });
      applied = true;
    });
    if (!applied) throw new ClaudeConnectorError(409, 'O estado da demanda mudou entre a leitura e a gravação por outra chamada nesse intervalo; nada foi alterado.');
    // O label no GitHub só é sincronizado DEPOIS que a escrita no Firestore foi confirmada pela
    // transação acima — nunca antes (achado do Codex na revisão do PR #9).
    const nextLabel = labelForState(nextState);
    const replaceStatusLabel = deps.github?.replaceStatusLabel ?? replaceGithubStatusLabel;
    await replaceStatusLabel(deps.githubToken, demand, nextLabel);
    await appendEvent(deps, demandId, systemId, 'demand.state-changed', { previous_state: demand.state, state: nextState, notes: String(input.notes || '').trim() });
    deps.sendEvent('devflow_demand_update', { sistema_id: systemId, demand: updatedDemand });
    return { success: true as const, demand: updatedDemand };
  } catch (error: any) {
    if (error instanceof ClaudeConnectorError) throw error;
    console.error('Erro ao marcar demanda como pronta para execução via conector Claude:', error);
    throw new ClaudeConnectorError(502, error.message || 'Não foi possível marcar a demanda como pronta para execução.');
  }
}
```

A tool MCP correspondente deixa explícito, na própria descrição, que ela não é portão humano — só bookkeeping entre os dois portões reais:

```ts
server.registerTool('argos_marcar_pronto_para_execucao', {
  description: 'Avança uma demanda de plan-approved (ou preparing) para ready-for-execution, sincronizando o label no GitHub. ' +
    'Passo de transição entre argos_aprovar_plano e argos_enfileirar_execucao. NÃO é portão humano: as decisões humanas de ' +
    'verdade já aconteceram (aprovar o plano) ou ainda vão acontecer (autorizar o enfileiramento) nas outras duas tools — ' +
    'esta apenas registra que a demanda está pronta, sem efeito irreversível, podendo ser chamada livremente.',
  inputSchema: {
    sistema,
    demanda_id: z.string().min(1).describe('Identificador da demanda a marcar como pronta para execução.'),
    notes: z.string().optional().describe('Observação opcional sobre a transição, registrada no evento.')
  },
  annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true }
}, async ({ sistema, demanda_id, notes }) => {
  try {
    return successResult(await operations.advanceToReadyForExecution({ systemId: sistema, demandId: demanda_id, notes }));
  } catch (error) { return errorResult(error); }
});
```

**5. Avanço real da demanda (06/09, 09:39:47) — primeiro uso de `argos_marcar_pronto_para_execucao`.** Estado mudou de `plan-approved` para `ready-for-execution`, label sincronizado no GitHub.

**6. Enfileiramento do job (06/09, 09:41) — segundo portão.** Novo pedido de autorização via Telegram/Hermes (tipo `enqueue-job`, solicitação `kSIbBMT22RGKvVcBFhHM`). De novo, a resposta do André no chat ("ok") foi ambígua — o Claude não presumiu aprovação e só prosseguiu depois de `consultar_autorizacao_argos` confirmar `aprovado` de forma independente. Na sequência, `consumir_autorizacao_argos` e `argos_enfileirar_execucao` criaram o job `DEV-2026-0002-implementation`, status `queued`.

**7. A segunda lacuna descoberta: nada executa o job automaticamente.** O `devflow-worker.ts` do `argos-gestor-sistemas` só expõe uma API de lease/report para um worker *externo* buscar o job, executá-lo fora deste backend e reportar o resultado — não existe hoje nenhum executor automático rodando, e não há tool MCP exposta para o Claude fechar esse ciclo (nem para o Claude atuar como esse worker). Diante disso, e com sua autorização explícita, o Claude aplicou a mudança diretamente, por fora do mecanismo de job/worker, usando a ponte com o computador do André:

```diff
--- a/lib/gemini.ts
+++ b/lib/gemini.ts
@@ -18,7 +18,7 @@ export const MODELOS_GEMINI = [
     descricao: 'Mais rápido e econômico — ideal para consultas do dia a dia',
   },
   {
-    id: 'gemini-3.7-flash',
+    id: 'gemini-3.8-flash',
     nome: 'Flash',
     descricao: 'Maior inteligência e precisão em raciocínio',
   },
@@ -27,6 +27,7 @@ export const MODELOS_GEMINI = [
 const MODELOS_LEGADOS: Record<string, string> = {
   'gemini-3.1-flash': 'gemini-3.7-flash',
   'gemini-3.6-flash': 'gemini-3.7-flash',
+  'gemini-3.7-flash': 'gemini-3.8-flash',
 };
```

O caminho até esse commit exigiu duas permissões pontuais do André: primeiro para conectar a pasta `sigex-gestao` (a tentativa inicial do Claude de pedir acesso sozinho foi bloqueada por um classificador de segurança do ambiente, então a conexão teve que ser feita manualmente pelo André no app desktop); depois para apagar arquivos dentro dela, quando um `git checkout` deixou um `.git/index.lock` travado (o `device_bash` não apaga arquivos por padrão). Antes de commitar, o Claude confirmou que a pasta local correspondia mesmo a `andre-martiini/gestao-sigex` (checando o `git remote`), rodou `tsc --noEmit` na raiz do projeto (sem erros novos — os dois erros pré-existentes são de módulos do Cloud Functions não instalados nesse ambiente, em `functions/src/index.ts`, sem relação com a mudança) e ignorou deliberadamente uma quantidade grande de arquivos com diffs de puro fim-de-linha (CRLF/LF) já presentes no working tree, não relacionados a esta tarefa. O commit `181f460`, na branch `claude/upgrade-gemini-flash-3.8`, contém só o arquivo `lib/gemini.ts`.

**8. Handoff para o Dev.** Sem credencial de push/PR, o Claude escreveu um prompt de handoff e o Dev externo deu push e abriu `andre-martiini/gestao-sigex#2` (`claude/upgrade-gemini-flash-3.8` → `main`).

## Onde o fluxo está agora

O PR #2 está aberto, ainda não mesclado — aguardando a revisão do Claude (novo procedimento) e o merge direto do André. Duas pontas ficaram em aberto e ainda não têm resposta:

Primeiro, o processo de deploy do `gestao-sigex` ainda não está confirmado. Diferente do `argos-gestor-sistemas` (Firebase App Hosting, com lançamento manual pelo console), este repositório não tem `.github/workflows`, `apphosting.yaml` nem qualquer automação de CI/CD identificada — é um projeto nascido no Google AI Studio (`gen-lang-client-0633332628`, hosting target `gestao-sigex-site`), e uma tentativa de consultar o histórico de releases no Console do Firebase para descobrir empiricamente esbarrou em "projeto não existe ou sem permissão" para a conta logada no navegador. Essa pergunta está pendente com o André.

Segundo, o job `DEV-2026-0002-implementation` continua com status `queued` no Firestore — porque a implementação real foi feita por fora do mecanismo de lease/report do `devflow-worker`, e não existe hoje uma tool MCP para o Claude "reportar" a conclusão desse job de volta ao DevFlow. O código está commitado e o PR está aberto, mas, do ponto de vista dos dados do Argos, o job segue como se nada tivesse sido feito. Fechar esse ciclo — seja expondo uma tool de report, seja o Claude assumindo formalmente o papel de worker — é o próximo gap de arquitetura a decidir, na mesma linha do que já aconteceu com o passo 4 acima.

Um terceiro item, menor e sem urgência: a descrição do parâmetro `sistema` nas tools do Argos ainda diz "o único sistema habilitado é '*'", quando o valor real exigido é o id do sistema (ex.: `gestao-sigex`) — bug cosmético identificado durante os testes, ainda não corrigido.
