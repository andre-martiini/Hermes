# tests/rules/

Testes de `firestore.rules` contra o Firestore Emulator. Não existem testes de regra no repositório hoje (confirmado por busca em P00 — ver `docs/autonomia/baseline.md`, seção 2). Populado a partir de P01, que corrige a regra geral (`match /{document=**} { allow read, write: if internalUser(); }`, achado A16) e precisa provar, com teste, que a correção não quebra os fluxos legítimos do app React/voz.

Usar o [Firestore Emulator](https://firebase.google.com/docs/rules/unit-tests) com o `@firebase/rules-unit-testing`. Não usar o Admin SDK para esses testes — o Admin SDK ignora as regras de segurança por padrão, então um teste escrito com ele não prova nada sobre a regra (essa distinção está explícita no passo 9 do P01 do plano).
