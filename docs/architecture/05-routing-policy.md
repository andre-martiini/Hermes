# Política de Roteamento — Hermes

## 1. Propósito

Este documento congela o schema, os critérios e a tabela de decisão do `RoutingAssessment`. Qualquer módulo que calcule ou consuma um assessment deve seguir exatamente este contrato.

---

## 2. Schema Congelado — `RoutingAssessment`

```ts
interface RoutingAssessment {
  route:         'deterministic' | 'orchestrated';
  approval_mode: 'automatic'    | 'confirm' | 'required';
  risk_level:    'low'          | 'medium'  | 'high';
  clarity_score:  number; // [0, 1] — quão bem definida é a demanda
  context_score:  number; // [0, 1] — quão rico é o contexto disponível
  impact_score:   number; // [0, 1] — quão significativo é o efeito esperado
  rationale:      string[]; // motivos legíveis por humanos
}
```

Versão do schema: **v1.0** (2026-04-11).

---

## 3. Definição dos Scores

### 3.1 `clarity_score` — Clareza da demanda

Mede o quão bem definida, estruturada e inequívoca é a entrada.

| Sinal | Efeito |
|-------|--------|
| Ponto de partida padrão | +0.45 |
| Texto total > 80 chars | +0.15 |
| Texto total > 220 chars | +0.10 |
| Origem manual | +0.10 |
| Origem whatsapp ou audio | −0.08 |
| Tipo de ação `deep` | −0.07 |

**Faixa interpretativa:**
- `>= 0.60` → demanda clara
- `0.45 – 0.59` → parcialmente clara
- `< 0.45` → ambígua

### 3.2 `context_score` — Riqueza do contexto

Mede o quanto o sistema tem de informação de suporte para tomar decisão ou agir.

| Sinal | Efeito |
|-------|--------|
| Ponto de partida padrão | +0.20 |
| Base RAG selecionada | +0.30 |
| Cada arquivo extra (máx. +0.30) | +0.12 × n |
| Contexto de reunião vinculado | +0.20 |

**Faixa interpretativa:**
- `>= 0.50` → contexto suficiente
- `0.35 – 0.49` → contexto parcial
- `< 0.35` → contexto insuficiente

### 3.3 `impact_score` — Impacto esperado da ação

Mede o efeito estrutural ou operacional que a ação pode ter.

| Sinal | Efeito base |
|-------|-------------|
| Tipo `fast` | 0.35 |
| Tipo `deep` | 0.72 |
| Origem `google` | +0.08 |
| Arquivos extras presentes | +0.08 |
| Contexto de reunião presente | +0.05 |

**Faixa interpretativa:**
- `>= 0.75` → impacto alto
- `0.50 – 0.74` → impacto médio
- `< 0.50` → impacto baixo

---

## 4. Tabela de Decisão

### 4.1 `route`

| Condição | Route |
|----------|-------|
| `tipo_acao == 'deep'` | `orchestrated` |
| `clarity_score < 0.50` | `orchestrated` |
| `context_score < 0.45` | `orchestrated` |
| `impact_score > 0.65` | `orchestrated` |
| Nenhuma das anteriores | `deterministic` |

### 4.2 `risk_level`

| Condição | Risk |
|----------|------|
| `impact_score >= 0.75` OU (`context_score < 0.35` E `clarity_score < 0.45`) | `high` |
| `impact_score >= 0.50` OU `context_score < 0.45` | `medium` |
| Nenhuma das anteriores | `low` |

### 4.3 `approval_mode`

| Condição | Approval |
|----------|----------|
| `risk_level == 'high'` OU (`tipo_acao == 'deep'` E `context_score < 0.40`) | `required` |
| `route == 'orchestrated'` OU `risk_level == 'medium'` | `confirm` |
| Nenhuma das anteriores | `automatic` |

**Prioridade de avaliação:** `required` > `confirm` > `automatic`.

---

## 5. Semântica dos Modos de Aprovação

| Modo | Significado operacional | Efeito na UI |
|------|------------------------|--------------|
| `automatic` | Copiloto e artefatos liberados sem intervenção | Sem card de governança |
| `confirm` | Uma confirmação curta antes de usar copiloto nesta sessão | Card âmbar — botão "Liberar sessão" |
| `required` | Liberação explícita obrigatória antes de qualquer ação assistida | Card vermelho — botão "Liberar sessão" |

---

## 6. Separação de Responsabilidades

| Tipo de sinal | Natureza | Sobrescrevível? |
|---------------|----------|-----------------|
| Inferência heurística de scores | Estimativa — pode ser refinada | Sim, por input do usuário |
| Regras de bloqueio por risk_level | Obrigatória — não deve ser contornada silenciosamente | Não |
| `rationale[]` | Informativo — não determina rota | N/A |

---

## 7. Fonte de Verdade

A implementação de referência do cálculo é `src/utils/routing.ts` — função `assessTaskRouting`.

Módulos que precisam de routing assessment em contextos sem tarefa (ex.: `SistemaExecutionView`) devem derivar os parâmetros do contexto disponível e chamar a mesma função. Não devem duplicar a lógica.

### Derivação recomendada para sistemas:

| Parâmetro | Derivação |
|-----------|-----------|
| `tipoAcao` | `'deep'` se status for `producao` ou `testes`; `'fast'` caso contrário |
| `origin` | `'manual'` |
| `inputText` | `objetivo_negocio \|\| nome do sistema` |
| `hasRagContext` | `!!github_rag_synced_at` |
| `extraContextFileCount` | número de work items ativos (proxy de contexto operacional) |

---

## 8. Exemplos Reais com Resultado Esperado

| Entrada | clarity | context | impact | route | risk | approval |
|---------|---------|---------|--------|-------|------|----------|
| Tarefa rápida manual, sem RAG, texto curto | ~0.55 | 0.20 | 0.35 | deterministic | low | automatic |
| Tarefa deep manual, com RAG e reunião | ~0.48 | 0.70 | 0.82 | orchestrated | high | required |
| Tarefa fast via WhatsApp, sem contexto | ~0.37 | 0.20 | 0.35 | orchestrated | medium | confirm |
| Sistema em produção com RAG sincronizado | ~0.55 | 0.50 | 0.80 | orchestrated | high | required |
| Sistema em ideia, sem repo sincronizado | ~0.55 | 0.20 | 0.35 | deterministic | low | automatic |

---

## 9. Riscos a Evitar

- **Não espalhar a lógica de cálculo em múltiplas telas.** Sempre chamar `assessTaskRouting`.
- **Não usar `approval_mode` só como indicador visual.** Deve bloquear ações assistidas no runtime.
- **Não ignorar `risk_level == 'high'` para conveniência de UX.** O card de governança deve aparecer sempre que necessário.
- **Não recalcular o assessment em cada render.** Usar `useMemo` com dependências estáveis.
