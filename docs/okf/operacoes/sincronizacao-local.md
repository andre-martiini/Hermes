---
type: runbook
title: Sincronização local (alternativa sem Cloud Function)
description: Por que e como rodar a sincronização Google Tasks via script Python local em vez de Cloud Function, para uso pessoal de baixa complexidade.
tags: [hermes, sincronizacao, google-tasks, local]
timestamp: 2026-05-19T17:30:42-03:00
---

# Sincronização local

## Por quê

A Cloud Function requer configurações de autenticação OAuth mais adequadas para ambientes com múltiplos usuários. Para uso pessoal, o script local (`hermes_cli.py watch`) é mais simples e confiável — ver alternativa em nuvem em [Deploy das Cloud Functions de sincronização](/docs/okf/operacoes/deploy-cloud-functions.md).

## Solução recomendada: iniciar junto com o dev server

### Opção 1 — `concurrently`

Em `package.json`:
```json
"scripts": {
  "dev": "concurrently \"vite\" \"python hermes_cli.py watch\"",
  "dev:web": "vite"
}
```
```bash
npm install --save-dev concurrently
```
Depois, `npm run dev` inicia frontend e sincronização juntos.

### Opção 2 — script Windows

`start.bat`:
```batch
@echo off
start "Hermes Web" cmd /k "npm run dev"
timeout /t 2
start "Hermes Sync" cmd /k "python hermes_cli.py watch"
```

## Futuro: migrar para Cloud Function

Quando quiser não depender de script local:
1. Criar API intermediária que gerencia credenciais OAuth.
2. Usar Firebase Functions com autenticação de serviço.
3. Implementar refresh token automático.

Ver [Deploy das Cloud Functions de sincronização](/docs/okf/operacoes/deploy-cloud-functions.md) para o fluxo completo quando essa migração for feita.
