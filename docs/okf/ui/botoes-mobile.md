---
type: decision
title: Ajuste de tamanho dos botões mobile
description: Redução do tamanho dos botões do menu principal e do cabeçalho mobile para evitar sobreposição e excesso de espaço ocupado.
resource: index.tsx
tags: [hermes, ui, mobile]
timestamp: 2026-05-19T17:30:42-03:00
---

# Ajuste de tamanho dos botões mobile

## Objetivo

Reduzir o tamanho dos botões do menu principal na versão mobile para melhorar a visualização e evitar sobreposição ou excesso de espaço ocupado.

## Alterações realizadas

### Tela inicial (Dashboard / Menu Principal)

Arquivo: `index.tsx`, seção dos cards de módulos ("Ações", "Financeiro", "Saúde", "Ferramentas", "Sistemas").

- Padding: `p-6` → `p-4` em mobile (mantido `md:p-6` no desktop).
- Ícones: `w-12 h-12` → `w-10 h-10` em mobile (mantido `md:w-12 md:h-12`).
- Fonte dos títulos: `text-xl` → `text-lg` em mobile.

### Cabeçalho mobile (Top Header)

Arquivo: `index.tsx`, seção do header mobile (botões de ação e menu sanduíche).

- Padding: `p-2.5`/`p-2` → `p-1.5`.
- Ícones SVG: `w-6 h-6` → `w-5 h-5`.
- Aplica-se aos botões: Voltar, Ideias Rápidas, Configurações, Notificações, Criar Ação e Menu Hambúrguer.

## Resultado esperado

- Cards da tela inicial mais compactos em dispositivos móveis.
- Barra de navegação superior acomoda melhor os ícones sem quebra de layout em telas pequenas.
