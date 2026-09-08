import { defineConfig } from "vitest/config";

// Config dedicado para os testes de firestore.rules — precisam do Firestore
// Emulator rodando (ver README.md deste diretório) e por isso são
// excluídos do `npm test` padrão (ver `test.exclude` em vite.config.ts na
// raiz). Rodado via `npm run test:rules`, que sobe o emulador primeiro.
export default defineConfig({
  test: {
    // Caminho relativo à raiz do repo (vitest resolve `root` como o
    // diretório de trabalho de onde o comando roda, não o diretório deste
    // arquivo de config) — restrito só a este diretório, para não
    // recolher testes de todo o resto do repo quando `test:rules` for
    // invocado a partir da raiz.
    include: ["tests/rules/**/*.test.ts"],
    environment: "node",
  },
});
