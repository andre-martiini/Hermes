# Baseline — P00

Levantamento real, executado nesta sessão, em ambiente isolado (sandbox sem acesso a produção, sem credenciais de serviço). Cada afirmação abaixo tem fonte e horário. O que não pôde ser verificado a partir daqui está listado explicitamente na seção 5, sem suposição.

Nota sobre referências: este arquivo e `functions/tests_autonomy/README.md` citam `docs/plano-hermes-autonomo-2026-09-06.md` (o plano completo) e "PR #184". Esse arquivo ainda **não está mergeado em `main`** no momento deste levantamento — existe no PR #184, aberto. A referência é intencional (é o documento que este pacote executa), mas por ora é um link para um arquivo que não existe neste branch; ficará resolvido quando o PR #184 for mergeado.

## 1. Estado do repositório

- Repositório: `andre-martiini/Hermes`.
- Branch: `main`.
- Commit no momento deste levantamento: `31d2cf959e7c755f8852001405e496382ef0b5d9` (merge do PR #183, "fix-elevacao-ultima-tentativa").
- Working tree: limpo (clone raso feito para este levantamento, sem alterações locais preexistentes).
- Verificado em: 2026-09-07, por leitura direta do repositório (não é o commit `46c874367b519aa95ade2a23b77f1dc6a1cdeb06` investigado no plano — main avançou por PRs mergeados depois daquela investigação).

## 2. Inventário de ferramentas e testes

| Item | Valor | Como foi medido |
|---|---|---|
| Schemas MCP (`functions/tools/schemas/*.json`) | 101 | contagem de arquivos |
| Entradas de catálogo correspondentes | 101 | contagem de `"name":` nos schemas |
| Arquivos `test_*.py` em `functions/` | 47 | `find`, excluindo `venv/` |
| Definições `def test_` nesses arquivos | 1148 | `grep -c`, excluindo `venv/` |
| `functions/main.py` | 16.175 linhas | `wc -l` |
| `functions/hermes_core_logic.py` | 6.012 linhas | `wc -l` |
| Testes de regra do Firestore (`tests/rules/`) | 0 — diretório não existe | `find` não encontrou nenhum arquivo |

O plano (PR #184) cita "47 arquivos test_*.py... 1.127 definições" no commit investigado; hoje são 1148 definições no mesmo conjunto de arquivos — crescimento esperado por commits posteriores (ex.: PR #183). O achado permanece válido em ordem de grandeza.

## 3. Gates executados agora (evidência de comportamento real, não relato)

**Frontend (`npm test` → vitest):** 248/248 passando, 20/20 arquivos de teste. `npm install` limpo (1195 pacotes, sem erro de build).

**Python (`python -m unittest discover -s functions -p "test_*.py"`, venv isolado com `functions/requirements.txt`):** 1146 testes executados, 1146 OK.

Ressalva importante encontrada durante a execução: os testes passam hoje, mas **não há isolamento de rede deliberado**. O log da execução mostra centenas de tentativas reais de chamada a serviços externos — Firestore (`Application Default Credentials`), API do Telegram, Gemini — que falham porque este sandbox não tem outbound/credencial para esses serviços, e o próprio código trata essas falhas como erro esperado (`except`). Ou seja: o "OK" de hoje depende do ambiente não ter rede para esses destinos, não de um bloqueio de rede construído para esse fim. Isso confirma, com evidência de execução (não só leitura de código), o item do plano "estabelecer bloqueio de rede por padrão nos testes novos" — ainda não existe.

## 4. CI/CD — o que o achado A17 do plano ainda descreve corretamente e o que já mudou

- **`pr.yml` já roda os testes Python** (job `python`, `unittest discover` em `functions/`), em paralelo ao job de frontend. Isso corrige a parte do A17 que dizia "testes Python nunca rodavam" — o próprio pr.yml documenta essa correção em comentário, então já era conhecida antes deste levantamento. Achado A17, nesta parte, está desatualizado em relação ao PR #184.
- **`deploy.yml` continua sem publicar `firestore.rules`** — o passo de deploy roda `firebase deploy --only hosting,functions,firestore:indexes,storage`. `firestore:rules` não está na lista. Isso significa que o conteúdo de `firestore.rules` no repositório (que já tem restrições específicas para `system/`, `automations/`, `atencao/` e `promessas_abertas/`) pode não corresponder ao que está publicado em produção — não foi possível confirmar o que está publicado agora (ver seção 5). Esta parte do A17 permanece válida.
- **Correção preparada, não publicada:** o conector Argos não conseguiu gravar em `.github/workflows/deploy.yml` — GitHub recusou com 403 ("refusing to allow a Personal Access Token to create or update workflow `.github/workflows/deploy.yml` without `workflow` scope"). O PAT usado pelo Argos não tem o escopo `workflow`. A correção (adicionar `firestore:rules` à lista `--only`) está descrita e pronta; alguém com esse escopo (ou o próprio André, editando direto no GitHub) precisa aplicá-la manualmente. Isso vale para qualquer alteração futura em `.github/workflows/*` neste plano — P01, P00 e P17 preveem mexer em CI.

## 5. Regra geral do Firestore (A16) — confirmado por leitura direta

`firestore.rules` atual:

```
match /system/{document=**}          { allow read, write: if false; }
match /automations/{document=**}     { allow read, write: if false; }
match /public_configs/{document=**}  { allow read, write: if internalUser(); }
match /whatsapp_messages/{document=**} { allow read, write: if internalUser(); }
match /atencao/{document=**}         { allow read: if internalUser(); allow write: if false; }
match /promessas_abertas/{document=**} { allow read: if internalUser(); allow write: if false; }
match /{document=**}                 { allow read, write: if internalUser(); }
```

O catch-all final ainda concede leitura/escrita irrestrita ao `internalUser` (a própria conta autenticada do André) para qualquer coleção não listada acima — inclusive as coleções novas que o plano propõe (`autonomy_policies`, `autonomy_decisions`, `operation_ledger` etc., seção 4.2). O achado A16 permanece válido e é o alvo direto do P01.

## 6. Não verificado a partir deste ambiente (marcado explicitamente, sem suposição)

- Regras efetivamente publicadas em produção agora (depende do último deploy real; não tenho acesso ao console Firebase nem a logs de deploy).
- Rotinas Cowork agendadas de fato vs. seus equivalentes Cloud Scheduler.
- Flags de autonomia/atenção realmente ativas em produção (`autonomy.*`, detectores da fila de atenção).
- Build SHA e `catalog_version` publicados no servidor MCP em produção.
- Estado de créditos/quota do Codex no momento em que cada PR deste plano for aberto (varia por PR).

## 7. Ambiente de teste isolado / emulador

Não configurado nesta PR. Os testes de lógica pura (a maioria dos 1146 atuais) não dependem de emulador — dependem apenas de não ter rede real disponível, o que hoje é acidental, não deliberado. Ligar o Firestore Emulator fica para quando P01 precisar de testes de transação/concorrência reais (lease, idempotência, regras) — é nesse ponto que um mock de rede não basta e um emulador de verdade se justifica. Esta PR cria a convenção e os diretórios (`functions/tests_autonomy/`, `tests/rules/`) que os pacotes seguintes vão popular.
