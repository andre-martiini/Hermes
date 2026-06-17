---
type: guide
title: Badges de sincronização de tarefas
description: Como o campo sync_status indica visualmente tarefas recém-criadas ou atualizadas pela sincronização com Google Tasks, e como implementá-lo no script de sincronização.
tags: [hermes, sincronizacao, ui, firestore]
timestamp: 2026-05-19T17:30:42-03:00
---

# Badges de sincronização de tarefas

## Visão geral

O Hermes suporta badges visuais para indicar tarefas recém-sincronizadas do Google Tasks.

## Campos na interface `Tarefa`

```typescript
interface Tarefa {
    // ... campos existentes ...
    sync_status?: 'new' | 'updated' | 'synced' | null;
    last_sync_date?: string; // ISO 8601
}
```

## Valores de `sync_status`

- `new`: tarefa criada na sincronização. Badge roxo/rosa com sino, animação pulsante, texto "NOVO".
- `updated`: tarefa existente atualizada. Badge amarelo/laranja com refresh, texto "ATUALIZADA".
- `synced` ou `null`: já processada, sem badge.

## Implementação em `hermes_cli.py`

Ao criar:
```python
nova_tarefa = {
    "id": task_id,
    "titulo": task_title,
    "sync_status": "new",
    "last_sync_date": datetime.now().isoformat()
}
db.collection('tarefas').document(task_id).set(nova_tarefa)
```

Ao atualizar (se `tarefa_mudou` detectar mudança nos campos `titulo`, `data_limite`, `status`, `notas`):
```python
updates = {
    "titulo": nova_versao["titulo"],
    "sync_status": "updated",
    "last_sync_date": datetime.now().isoformat()
}
tarefa_ref.update(updates)
```

Limpeza automática após 24h (volta para `synced`):
```python
def limpar_badges_antigos():
    limite = (datetime.now() - timedelta(hours=24)).isoformat()
    tarefas = db.collection('tarefas').where(
        'last_sync_date', '<', limite
    ).where('sync_status', 'in', ['new', 'updated']).stream()
    for tarefa in tarefas:
        db.collection('tarefas').document(tarefa.id).update({'sync_status': 'synced'})
```

## Comportamento visual por componente

- `RowCard`: badge ao lado de projeto/categoria, 9px, pulse em "Novo".
- `PgcMiniTaskCard`: badge na linha de metadados, 7px, pulse em "Novo".
- Tabela de não classificadas: badge inline com o título, 8px, pulse em "Novo".

## Cores

- Novo: gradiente roxo → rosa (`from-purple-500 to-pink-500`).
- Atualizada: gradiente amarelo → laranja (`from-amber-400 to-orange-500`).

## Recomendações

1. Sempre definir `last_sync_date` ao criar/atualizar tarefas.
2. Executar `limpar_badges_antigos()` periodicamente (sugestão: 24h).
3. Logar sincronizações para auditoria.
4. Considerar timezone ao comparar datas.
