# Plano de Implementação: Ajuste de Tamanho dos Botões Mobile

## Objetivo
Reduzir o tamanho dos botões do menu principal na versão mobile para melhorar a visualização e evitar sobreposição ou excesso de espaço ocupado.

## Alterações Realizadas

### 1. Tela Inicial (Dashboard / Menu Principal)
- **Arquivo**: `index.tsx`
- **Seção**: Cards dos Módulos ("Ações", "Financeiro", "Saúde", "Ferramentas", "Sistemas")
- **Alteração**:
  - Redução do padding de `p-6` para `p-4` em telas mobile (mantido `md:p-6` para desktop).
  - Redução do tamanho dos ícones de `w-12 h-12` para `w-10 h-10` em mobile (mantido `md:w-12 md:h-12` para desktop).
  - Ajuste do tamanho da fonte dos títulos de `text-xl` para `text-lg` em mobile.

### 2. Cabeçalho Mobile (Top Header)
- **Arquivo**: `index.tsx`
- **Seção**: Mobile Header (botões de ação e menu sanduíche)
- **Alteração**:
  - Redução do padding de `p-2.5` (ou `p-2`) para `p-1.5`.
  - Redução do tamanho dos ícones SVG de `w-6 h-6` para `w-5 h-5`.
  - Isso se aplica aos botões: Voltar, Ideias Rápidas, Configurações, Notificações, Criar Ação e Menu Hambúrguer.

## Resultado Esperado
- Os cards na tela inicial ficam mais compactos em dispositivos móveis.
- A barra de navegação superior (header) acomoda melhor os ícones sem quebra de layout ou poluição visual em telas pequenas.
