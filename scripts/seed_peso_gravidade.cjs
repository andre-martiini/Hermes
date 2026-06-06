/**
 * Inicializa o campo `peso_gravidade` (1..5) nas Áreas Temáticas (coleção `unidades`).
 *
 * Regra (Score GUT - variável G):
 *   - CLC e Assistência Estudantil  -> 5 (máxima gravidade institucional)
 *   - Demais áreas sem peso definido -> 1 (default)
 *   - Áreas que já possuem peso_gravidade válido (1..5) são preservadas
 *     (exceto CLC/Assistência, que são sempre forçadas para 5).
 *
 * Uso:
 *   node scripts/seed_peso_gravidade.cjs           # dry-run (apenas relatório)
 *   node scripts/seed_peso_gravidade.cjs --apply   # aplica as alterações
 */
const admin = require('firebase-admin');

admin.initializeApp({ projectId: 'gestao-hermes' });
const db = admin.firestore();

const APPLY = process.argv.includes('--apply');

const norm = (s) => (s || '').trim().toUpperCase();

// Heurística para identificar as áreas institucionais de gravidade máxima.
const isMaxGravity = (nome) => {
  const n = norm(nome);
  return n.includes('CLC') || n.includes('ASSIST'); // ASSISTÊNCIA (ESTUDANTIL)
};

const isValidPeso = (v) => Number.isInteger(v) && v >= 1 && v <= 5;

async function run() {
  const snap = await db.collection('unidades').get();
  const updates = [];

  snap.forEach((doc) => {
    const data = doc.data() || {};
    const nome = data.nome || '(sem nome)';
    const atual = data.peso_gravidade;

    let alvo;
    if (isMaxGravity(nome)) {
      alvo = 5;
    } else if (isValidPeso(atual)) {
      alvo = atual; // preserva o que já está válido
    } else {
      alvo = 1; // default
    }

    if (alvo !== atual) {
      updates.push({ id: doc.id, nome, de: atual, para: alvo });
    }
  });

  console.log(`Total de áreas (unidades): ${snap.size}`);
  console.log(`A atualizar: ${updates.length}\n`);
  updates.forEach((u) =>
    console.log(`  [${u.id}] "${u.nome}"  G: ${u.de === undefined ? '(vazio)' : u.de} -> ${u.para}`)
  );

  if (updates.length === 0) {
    console.log('\nNada a fazer.');
    return;
  }

  if (!APPLY) {
    console.log('\n(DRY-RUN) Rode com --apply para gravar as alterações.');
    return;
  }

  let done = 0;
  for (let i = 0; i < updates.length; i += 400) {
    const batch = db.batch();
    for (const u of updates.slice(i, i + 400)) {
      batch.update(db.collection('unidades').doc(u.id), { peso_gravidade: u.para });
    }
    await batch.commit();
    done += Math.min(400, updates.length - i);
    console.log(`Lote aplicado: ${done}/${updates.length}`);
  }
  console.log(`\nConcluído: ${done} áreas atualizadas.`);
}

run().catch((e) => {
  console.error('Erro:', e);
  process.exit(1);
});
