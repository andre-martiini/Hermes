---
type: guide
title: Guia rápido (Quickstart)
description: Como iniciar o Hermes localmente, manual ou automaticamente, e estrutura básica do projeto.
tags: [hermes, quickstart, setup]
timestamp: 2026-05-19T17:30:42-03:00
---

# Guia rápido — Hermes

## Iniciar o sistema (mais fácil)

```bash
.\start.bat
```

Abre automaticamente:
- Frontend web (http://localhost:5173)
- Sincronização com Google Tasks (em background)

## Ou iniciar manualmente

Terminal 1 — frontend:
```bash
npm run dev
```

Terminal 2 — sincronização:
```bash
python hermes_cli.py watch
```

## Como usar

1. Abra http://localhost:5173
2. Clique em "Sync Google" para sincronizar tarefas
3. A sincronização também acontece automaticamente em background

## Estrutura

- `start.bat` — inicia tudo automaticamente (recomendado)
- `index.tsx` — aplicação web principal
- `hermes_cli.py` — script de sincronização local
- `functions/` — Cloud Functions (deploy em nuvem)

## Próximos passos (opcional)

Para deployar uma Cloud Function e não depender do script local, ver [Deploy das Cloud Functions de sincronização](/docs/okf/operacoes/deploy-cloud-functions.md). Para uso pessoal, `start.bat` já é suficiente — ver também [Sincronização local](/docs/okf/operacoes/sincronizacao-local.md).
