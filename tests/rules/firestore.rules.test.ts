/**
 * Testes de firestore.rules contra o Firestore Emulator, via
 * @firebase/rules-unit-testing (não o Admin SDK — o Admin SDK ignora as
 * regras de segurança por padrão, então um teste escrito com ele não prova
 * nada sobre a regra; ver tests/rules/README.md e o passo 9 do P01 do
 * plano de autonomia).
 *
 * Cobre o achado A16 (P01, passos 7-8): a regra geral antiga
 * `match /{document=**} { allow read, write: if internalUser(); }` não
 * isolava coleções de política/autorização/execução (idempotency,
 * mcp_audit_log, agent_requests, agent_runs, mcp_jobs,
 * promocoes_autonomia_sugeridas, telegram_sessions, whitelist) — qualquer
 * cliente autenticado como o dono tinha leitura/escrita irrestrita nelas,
 * mesmo sendo coleções que só as Cloud Functions (Admin SDK) devem tocar.
 *
 * A primeira versão da correção (blocos `match` irmãos com `if false` por
 * coleção, ao lado do catch-all antigo) foi pega por revisão adversarial
 * como um NO-OP para o dono: no Firestore, quando mais de um bloco `match`
 * casa com o mesmo caminho, o acesso é concedido por UNIÃO (OR) das
 * condições, não pelo bloco mais específico — exatamente o que o próprio
 * achado A16 do plano já descrevia ("regra geral... sobrepondo restrições
 * específicas"). Corrigido consolidando tudo num ÚNICO bloco `match`, com
 * a exclusão de coleções de controle expressa DENTRO da condição (ver
 * firestore.rules) — não existem mais blocos `match` irmãos neste arquivo
 * de regras, então essa classe de bug não pode mais ocorrer aqui.
 *
 * Os testes cobrem exatamente os três perfis exigidos pelo passo de testes
 * do P01 no plano: usuário público (não autenticado), cliente autenticado
 * mas não-dono, e o próprio dono (internalUser) — nas coleções de
 * controle, NENHUM dos três pode ler ou escrever diretamente; numa coleção
 * de uso legítimo do frontend (ex.: tarefas), o dono continua podendo
 * (regressão contra o achado A16 quebrar o app ao fechar o catch-all,
 * achado A16 passo 8).
 *
 * IMPORTANTE (honestidade epistêmica, ver docs/autonomia/execucao.md sub-
 * entrega 5/N): este arquivo foi escrito seguindo a API pública documentada
 * de @firebase/rules-unit-testing (initializeTestEnvironment/assertFails/
 * assertSucceeds) e a sintaxe das regras foi revisada manualmente com
 * cuidado (incluindo a correção do bug de OR entre `match` acima, pega por
 * uma revisão adversarial dedicada), mas NÃO foi executado contra um
 * Firestore Emulator real neste ambiente — o sandbox de desenvolvimento
 * não tem acesso de rede para storage.googleapis.com, necessário para
 * baixar o binário do emulador (bloqueio de política de rede da
 * organização, não específico deste teste). Rodar com:
 *
 *   npm run test:rules
 *
 * a partir de um ambiente com acesso a storage.googleapis.com (a própria
 * máquina do André, ou um runner de CI com rede irrestrita) antes de
 * considerar este teste validado de ponta a ponta.
 */
import { afterAll, beforeAll, describe, it } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
  RulesTestEnvironment,
} from '@firebase/rules-unit-testing';
import { doc, getDoc, setDoc } from 'firebase/firestore';

const PROJECT_ID = 'demo-hermes-rules-test';
const DONO_EMAIL = 'andre.martiini@gmail.com';

// Coleções de política/autorização/execução fechadas nesta sub-entrega
// (achado A16, P01 passo 7) — só Cloud Functions (Admin SDK) as tocam.
const COLECOES_DE_CONTROLE = [
  'idempotency',
  'mcp_audit_log',
  'agent_requests',
  'agent_runs',
  'mcp_jobs',
  'promocoes_autonomia_sugeridas',
  'telegram_sessions',
  'whitelist',
];

let testEnv: RulesTestEnvironment;

beforeAll(async () => {
  const rules = fs.readFileSync(
    path.resolve(__dirname, '../../firestore.rules'),
    'utf8',
  );
  testEnv = await initializeTestEnvironment({
    projectId: PROJECT_ID,
    firestore: { rules },
  });
});

afterAll(async () => {
  await testEnv?.cleanup();
});

describe('firestore.rules — coleções de controle (achado A16)', () => {
  for (const colecao of COLECOES_DE_CONTROLE) {
    describe(`coleção "${colecao}"`, () => {
      it('usuário público (não autenticado) não pode ler nem escrever', async () => {
        const db = testEnv.unauthenticatedContext().firestore();
        const ref = doc(db, colecao, 'doc-teste');
        await assertFails(getDoc(ref));
        await assertFails(setDoc(ref, { x: 1 }));
      });

      it('cliente autenticado mas não-dono não pode ler nem escrever', async () => {
        const db = testEnv
          .authenticatedContext('terceiro-uid', {
            email: 'terceiro@example.com',
            email_verified: true,
          })
          .firestore();
        const ref = doc(db, colecao, 'doc-teste');
        await assertFails(getDoc(ref));
        await assertFails(setDoc(ref, { x: 1 }));
      });

      it('o próprio dono (internalUser) também não pode ler nem escrever diretamente', async () => {
        // Ponto central do achado A16: mesmo a conta do dono, autenticada
        // e com e-mail verificado, não deve ter acesso direto a estas
        // coleções — só as Cloud Functions (Admin SDK) as tocam.
        const db = testEnv
          .authenticatedContext('dono-uid', {
            email: DONO_EMAIL,
            email_verified: true,
          })
          .firestore();
        const ref = doc(db, colecao, 'doc-teste');
        await assertFails(getDoc(ref));
        await assertFails(setDoc(ref, { x: 1 }));
      });
    });
  }
});

describe('firestore.rules — coleções já denegadas por completo (regressão)', () => {
  for (const colecao of ['system', 'automations']) {
    it(`"${colecao}": nem o dono tem acesso direto (comportamento pré-existente, não deve regredir)`, async () => {
      const db = testEnv
        .authenticatedContext('dono-uid', {
          email: DONO_EMAIL,
          email_verified: true,
        })
        .firestore();
      const ref = doc(db, colecao, 'doc-teste');
      await assertFails(getDoc(ref));
      await assertFails(setDoc(ref, { x: 1 }));
    });
  }
});

describe('firestore.rules — fluxos legítimos do frontend não quebram (achado A16 passo 8)', () => {
  it('dono (internalUser) continua podendo ler e escrever em "tarefas" (catch-all)', async () => {
    const db = testEnv
      .authenticatedContext('dono-uid', {
        email: DONO_EMAIL,
        email_verified: true,
      })
      .firestore();
    const ref = doc(db, 'tarefas', 'tarefa-teste');
    await assertSucceeds(setDoc(ref, { titulo: 'teste' }));
    await assertSucceeds(getDoc(ref));
  });

  it('usuário público não pode ler nem escrever em "tarefas"', async () => {
    const db = testEnv.unauthenticatedContext().firestore();
    const ref = doc(db, 'tarefas', 'tarefa-teste');
    await assertFails(getDoc(ref));
    await assertFails(setDoc(ref, { titulo: 'teste' }));
  });

  it('dono (internalUser) continua podendo ler e escrever em "public_configs" (regra explícita pré-existente)', async () => {
    const db = testEnv
      .authenticatedContext('dono-uid', {
        email: DONO_EMAIL,
        email_verified: true,
      })
      .firestore();
    const ref = doc(db, 'public_configs', 'config-teste');
    await assertSucceeds(setDoc(ref, { chave: 'valor' }));
    await assertSucceeds(getDoc(ref));
  });

  it('"atencao": dono pode ler mas não escrever direto (regra explícita pré-existente, sem regressão)', async () => {
    const db = testEnv
      .authenticatedContext('dono-uid', {
        email: DONO_EMAIL,
        email_verified: true,
      })
      .firestore();
    const ref = doc(db, 'atencao', 'item-teste');
    await assertSucceeds(getDoc(ref));
    await assertFails(setDoc(ref, { titulo: 'teste' }));
  });

  it('"promessas_abertas": dono pode ler mas não escrever direto (mesma regra de "atencao", isColecaoSomenteLeitura)', async () => {
    const db = testEnv
      .authenticatedContext('dono-uid', {
        email: DONO_EMAIL,
        email_verified: true,
      })
      .firestore();
    const ref = doc(db, 'promessas_abertas', 'item-teste');
    await assertSucceeds(getDoc(ref));
    await assertFails(setDoc(ref, { titulo: 'teste' }));
  });
});
