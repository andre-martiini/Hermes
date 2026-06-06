/**
 * Reclassifica tarefas cuja `area_tematica` foi "inventada" (não corresponde a nenhuma
 * Unidade existente nem a GERAL / NÃO CLASSIFICADA).
 *
 * Estratégia (decisão do usuário): mapear as ÓBVIAS para a Unidade correspondente e
 * mandar o resto para 'GERAL'. O alvo de cada alias é resolvido dinamicamente a partir
 * dos nomes reais das Unidades (evita criar variações com acento/traço errados).
 *
 * Uso:
 *   node scripts/reclassify_invented_areas.cjs           # dry-run (apenas relatório)
 *   node scripts/reclassify_invented_areas.cjs --apply   # aplica as alterações
 */
const admin = require('firebase-admin');

admin.initializeApp({ projectId: 'gestao-hermes' });
const db = admin.firestore();

const APPLY = process.argv.includes('--apply');

function norm(s) {
  return (s || '').trim().toUpperCase();
}

async function run() {
  // 1) Conjunto de áreas válidas (= Unidades UPPER + GERAL/NÃO CLASSIFICADA)
  const unidadesSnap = await db.collection('unidades').get();
  const unidadeNames = [];
  unidadesSnap.forEach(d => {
    const nome = norm((d.data() || {}).nome);
    if (nome) unidadeNames.push(nome);
  });
  const validas = new Set(['GERAL', 'NÃO CLASSIFICADA', ...unidadeNames]);

  // Resolve o nome EXATO de uma Unidade que contenha o trecho informado
  const findUnit = (needle) => unidadeNames.find(n => n.includes(norm(needle))) || null;

  // 2) Mapeamento de aliases óbvios -> Unidade existente (resolvido dinamicamente)
  const aliasRules = {
    'ASSISTÊNCIA': findUnit('ASSISTÊNCIA ESTUDANTIL'),
    'GCA': findUnit('GCA'),
    'SISTEMA DE GESTÃO REFORÇO POSITIVO': findUnit('GESTÃO REFORÇO POSITIVO'),
    'MEC SUSTENTÁVEL': findUnit('MEC SUSTENTÁVEL'),
  };

  console.log('Aliases resolvidos:');
  for (const [k, v] of Object.entries(aliasRules)) {
    console.log(`  ${k}  ->  ${v || '(NÃO ENCONTRADO -> GERAL)'}`);
  }
  console.log('');

  // 3) Decide o destino de uma área inventada
  const resolveTarget = (area) => aliasRules[norm(area)] || 'GERAL';

  // 4) Varre as tarefas
  const tarefasSnap = await db.collection('tarefas').get();
  const updates = [];
  tarefasSnap.forEach(doc => {
    const data = doc.data() || {};
    const area = data.area_tematica;
    if (!area || !String(area).trim()) return;        // vazia: não é "inventada"
    if (validas.has(norm(area))) return;              // já é válida
    updates.push({ id: doc.id, titulo: data.titulo || '(sem título)', de: area, para: resolveTarget(area) });
  });

  const mapeadas = updates.filter(u => u.para !== 'GERAL');
  const paraGeral = updates.filter(u => u.para === 'GERAL');

  console.log(`Total de tarefas: ${tarefasSnap.size}`);
  console.log(`Inventadas: ${updates.length}  (mapeadas p/ Unidade: ${mapeadas.length} | p/ GERAL: ${paraGeral.length})\n`);
  console.log('--- MAPEADAS PARA UNIDADE ---');
  mapeadas.forEach(u => console.log(`  [${u.id}] "${u.de}" -> "${u.para}"  (${u.titulo})`));
  console.log('\n--- PARA GERAL ---');
  paraGeral.forEach(u => console.log(`  [${u.id}] "${u.de}" -> GERAL  (${u.titulo})`));

  if (updates.length === 0) { console.log('\nNada a fazer.'); return; }

  if (!APPLY) {
    console.log('\n(DRY-RUN) Rode com --apply para gravar as alterações.');
    return;
  }

  // 5) Aplica em lotes de 400
  let done = 0;
  for (let i = 0; i < updates.length; i += 400) {
    const batch = db.batch();
    for (const u of updates.slice(i, i + 400)) {
      batch.update(db.collection('tarefas').doc(u.id), { area_tematica: u.para });
    }
    await batch.commit();
    done += Math.min(400, updates.length - i);
    console.log(`Lote aplicado: ${done}/${updates.length}`);
  }
  console.log(`\nConcluído: ${done} tarefas reclassificadas.`);
}

run().catch(e => { console.error('Erro:', e); process.exit(1); });
