---
type: reference
title: Convenções de frontend
description: Stack, estrutura de pastas, padrões de componentes, estilo e testes do frontend React/TypeScript do Hermes.
resource: types.ts
tags: [hermes, okf, frontend, react, typescript, arquitetura]
timestamp: 2026-06-17T00:00:00Z
---

# Convenções de frontend

## Stack

React 19 + TypeScript ~5.8 (strict) + Vite 6 + TailwindCSS 3.4 + Firebase SDK 12.9. Testes com Vitest + Testing Library. Sem React Router — navegação manual por estado. Sem Context API/Redux/Zustand — estado local com `useState`/`useEffect` e callbacks via props.

Scripts principais (`package.json`): `npm run dev` (Vite, porta 3001, PWA habilitado), `npm run build`, `npm test` (Vitest).

## Estrutura de pastas

- **Raiz do projeto:** views grandes ficam direto na raiz (`FinanceView.tsx`, `HealthView.tsx`, `KnowledgeView.tsx`, `DashboardView.tsx`, `ContactsView.tsx`, `BolsistasView.tsx`, `ProjectsView.tsx`...), junto com `index.tsx` (entrypoint), `types.ts` (fonte única de tipos), `constants.tsx` e `firebase.ts`.
- **`src/components/`:** componentes reutilizáveis, organizados em subpastas por função: `ui/` (componentes base como `UIComponents.tsx`), `modals/` (`Modals.tsx`, `QuickNoteModal.tsx`), `tools/` (ferramentas como `HermesCopilotoDrawer.tsx`, `ShoppingListTool.tsx`), `calendar/`, `projects/`, `public/` (portais públicos).
- **`src/views/`:** views secundárias/rotas (`CalendarView.tsx`, `RAGBasesView.tsx`, `TaskExecutionView.tsx`, `ServicesView.tsx`...).
- **`src/services/`:** camada de serviço para chamadas a Cloud Functions — hoje só `knowledgeService.ts`; a maioria dos componentes ainda chama Firestore/Functions direto.
- **`src/utils/`:** funções puras e lógica de domínio (`knowledgeLogic.ts`, `calendarUtils.ts`, `pdfGenerator.ts`, `destructiveActions.ts`...).

Não há convenção rígida de "um arquivo por feature": views maiores acumulam vários componentes auxiliares no mesmo arquivo (ex.: `KnowledgeView.tsx`, 60K).

## Padrão de componentes

Function components com hooks, tipados via `interface NomeProps`. `React.memo` é usado em componentes que recebem props complexas (`PgcMiniTaskCard`, `RowCard`). Estado é local; comunicação entre componentes pai/filho é via callbacks em props — não há Context API nem store global.

```typescript
interface FerramentasViewProps {
  ideas: BrainstormIdea[];
  onDeleteIdea: (id: string) => void;
  isDark?: boolean;
}

export const FerramentasView: React.FC<FerramentasViewProps> = ({ ideas, onDeleteIdea, isDark = false }) => {
  const [isProcessing, setIsProcessing] = useState(false);
  // ...
};
```

Chamadas a Firestore/Cloud Functions costumam ficar direto no componente (sem camada de serviço):

```typescript
import { collection, onSnapshot, query, orderBy } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { db, functions } from '../../firebase';

useEffect(() => {
  const unsubscribe = onSnapshot(query(collection(db, 'tarefas'), orderBy('data_criacao', 'desc')), (snap) => {
    setTarefas(snap.docs.map(d => ({ id: d.id, ...d.data() })));
  });
  return () => unsubscribe();
}, []);
```

## Padrão de services

Onde existe (`src/services/knowledgeService.ts`), o padrão é: função `async` tipada com `httpsCallable<Input, Output>`, retornando `res.data` direto, sem try/catch (erro propaga para quem chama).

```typescript
export async function smartSearchKG(query: string, filtros: KnowledgeFilters = {}): Promise<SmartSearchResponse> {
  const fn = httpsCallable<{ query: string; filtros?: KnowledgeFilters }, SmartSearchResponse>(functions, 'smart_search_kg');
  const res = await fn({ query, filtros });
  return res.data;
}
```

## Tipos

`types.ts` na raiz (832 linhas) é a fonte única de tipos de domínio (`Tarefa`, `Toast`, `HealthWeight`, etc.) e também exporta funções utilitárias de formatação (`formatDate`, `formatDateLocalISO`). Componentes importam via alias `@/types`. Exceção: `knowledgeService.ts` define seus próprios tipos locais, por ser uma camada isolada.

## Estilização

TailwindCSS com tema customizado em `tailwind.config.js`: cores nomeadas (`surface`, `on-surface`, `primary-tactile`, `accent-tactile`, `safety-red`, `highlighter`), fontes (`Newsreader` serif, `JetBrains Mono`, `DSEG7Classic` para displays tipo LCD) e sombras customizadas (`shadow-soft-touch`, `shadow-lcd-panel`). Dark mode é condicional via prop (`isDark`/`isDarkTheme`) nas classes, não via media query. Sem CSS modules — tudo inline via classes Tailwind.

## Testes

Vitest + Testing Library. Arquivos `*.test.ts`/`*.test.tsx` ficam ao lado do código testado (ex.: `src/utils/destructiveActions.test.ts`, `src/components/NFSeGenerator.test.tsx`, `src/views/DiarioBordoUI.test.tsx`). `npm test` hoje roda só um subconjunto explícito de arquivos — ao adicionar testes novos, adicionar o caminho ao script em `package.json`.

## Navegação

Sem React Router. `index.tsx` mantém um `viewMode` (`useState`) que controla renderização condicional das views principais, e sincroniza com a URL via `window.history.pushState` + listener de `popstate`. Há também um evento customizado (`hermes:navigate`, em `src/utils/internalNavigation.ts`) para navegação interna disparada por outros componentes. Sub-views dentro de uma view usam o mesmo padrão (`useState` local, ex.: `pgcSubView`).

## Convenções de nomenclatura

- Componentes: `PascalCase.tsx` (ex.: `FerramentasView.tsx`).
- Utils/services: `camelCase.ts` (ex.: `knowledgeLogic.ts`).
- Interfaces de props: sufixo `Props` (ex.: `TimeGridProps`).
- Constantes globais: `UPPER_SNAKE_CASE`.
- Idioma: domínio e UI majoritariamente em português (`Tarefa`, `area_tematica`, `data_limite`); padrões/APIs do React em inglês (`useState`, `React.FC`).
