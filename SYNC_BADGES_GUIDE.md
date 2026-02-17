# Guia de Integração: Badges de Sincronização

## Visão Geral
O sistema Hermes agora suporta badges visuais para indicar tarefas que foram recém-sincronizadas do Google Tasks.

## Campos Adicionados à Interface Tarefa

```typescript
interface Tarefa {
    // ... campos existentes ...
    sync_status?: 'new' | 'updated' | 'synced' | null;
    last_sync_date?: string; // ISO 8601 format
}
```

## Valores de sync_status

- **'new'**: Tarefa foi criada pela primeira vez na sincronização
  - Badge: Roxo/Rosa com ícone de sino e animação pulsante
  - Texto: "NOVO"

- **'updated'**: Tarefa existente foi atualizada na sincronização
  - Badge: Amarelo/Laranja com ícone de refresh
  - Texto: "ATUALIZADA"

- **'synced'** ou **null**: Tarefa já foi visualizada/processada
  - Sem badge visível

## Como Implementar no Script de Sincronização (hermes_cli.py)

### 1. Ao Criar Nova Tarefa

```python
nova_tarefa = {
    "id": task_id,
    "titulo": task_title,
    # ... outros campos ...
    "sync_status": "new",
    "last_sync_date": datetime.now().isoformat()
}

# Adicionar ao Firestore
db.collection('tarefas').document(task_id).set(nova_tarefa)
```

### 2. Ao Atualizar Tarefa Existente

```python
# Buscar tarefa existente
tarefa_ref = db.collection('tarefas').document(task_id)
tarefa_atual = tarefa_ref.get().to_dict()

# Verificar se houve mudanças significativas
if tarefa_mudou(tarefa_atual, nova_versao):
    updates = {
        "titulo": nova_versao["titulo"],
        # ... outros campos atualizados ...
        "sync_status": "updated",
        "last_sync_date": datetime.now().isoformat()
    }
    tarefa_ref.update(updates)
```

### 3. Limpeza Automática (Opcional)

Após 24 horas, limpar o status de sincronização:

```python
from datetime import datetime, timedelta

def limpar_badges_antigos():
    """Remove badges de sincronização de tarefas com mais de 24h"""
    limite = (datetime.now() - timedelta(hours=24)).isoformat()
    
    tarefas = db.collection('tarefas').where(
        'last_sync_date', '<', limite
    ).where(
        'sync_status', 'in', ['new', 'updated']
    ).stream()
    
    for tarefa in tarefas:
        db.collection('tarefas').document(tarefa.id).update({
            'sync_status': 'synced'
        })
```

## Exemplo Completo de Sincronização

```python
def sincronizar_tarefa_google(google_task):
    """
    Sincroniza uma tarefa do Google Tasks para o Firestore
    """
    task_id = google_task['id']
    tarefa_ref = db.collection('tarefas').document(task_id)
    
    # Verificar se tarefa já existe
    tarefa_existente = tarefa_ref.get()
    
    # Preparar dados da tarefa
    tarefa_data = {
        "titulo": google_task['title'],
        "data_limite": google_task.get('due', ''),
        "status": "concluído" if google_task.get('status') == 'completed' else "em andamento",
        "notas": google_task.get('notes', ''),
        "last_sync_date": datetime.now().isoformat()
    }
    
    if not tarefa_existente.exists:
        # Nova tarefa
        tarefa_data.update({
            "id": task_id,
            "projeto": "GERAL",
            "prioridade": "média",
            "categoria": "NÃO CLASSIFICADA",
            "contabilizar_meta": True,
            "data_criacao": datetime.now().isoformat(),
            "sync_status": "new"  # 🎯 Badge "NOVO"
        })
        tarefa_ref.set(tarefa_data)
        print(f"✨ Nova tarefa criada: {tarefa_data['titulo']}")
        
    else:
        # Tarefa existente - verificar mudanças
        dados_antigos = tarefa_existente.to_dict()
        
        if tarefa_mudou(dados_antigos, tarefa_data):
            tarefa_data["sync_status"] = "updated"  # 🎯 Badge "ATUALIZADA"
            tarefa_ref.update(tarefa_data)
            print(f"🔄 Tarefa atualizada: {tarefa_data['titulo']}")
        else:
            # Sem mudanças significativas
            tarefa_ref.update({"last_sync_date": datetime.now().isoformat()})

def tarefa_mudou(antiga, nova):
    """Verifica se houve mudanças significativas"""
    campos_importantes = ['titulo', 'data_limite', 'status', 'notas']
    return any(antiga.get(campo) != nova.get(campo) for campo in campos_importantes)
```

## Comportamento Visual

### RowCard (Lista Principal)
- Badge aparece ao lado do projeto e categoria
- Tamanho: 9px
- Animação: Pulse para "Novo"

### PgcMiniTaskCard (Cards Pequenos)
- Badge aparece na linha de metadados
- Tamanho: 7px
- Animação: Pulse para "Novo"

### Tabela de Não Classificadas
- Badge aparece inline com o título
- Tamanho: 8px
- Animação: Pulse para "Novo"

## Recomendações

1. **Sempre definir last_sync_date** ao criar ou atualizar tarefas
2. **Executar limpeza periódica** dos badges antigos (sugestão: 24h)
3. **Logar as sincronizações** para auditoria
4. **Considerar timezone** ao comparar datas

## Cores dos Badges

- **Novo**: Gradiente roxo → rosa (`from-purple-500 to-pink-500`)
- **Atualizada**: Gradiente amarelo → laranja (`from-amber-400 to-orange-500`)
