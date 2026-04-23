const admin = require('firebase-admin');

// Inicializa a aplicação usando credenciais do ambiente
admin.initializeApp();

const db = admin.firestore();

async function backfillSistemas() {
  try {
    console.log("Iniciando backfill de nomes na coleção 'sistemas'...");

    const sistemasRef = db.collection('sistemas');
    const snapshot = await sistemasRef.get();

    if (snapshot.empty) {
      console.log("Nenhum documento encontrado na coleção 'sistemas'.");
      return;
    }

    // Configurando batch writes.
    // O Firestore suporta no máximo 500 operações por lote.
    let batch = db.batch();
    let batchCount = 0;
    let totalUpdated = 0;

    for (const doc of snapshot.docs) {
      const data = doc.data();
      const repoUrl = data.repositorio_principal;

      // Se não tiver repositório, não temos muito o que extrair
      if (!repoUrl) {
        console.log(`[SKIP] ID: ${doc.id} - Não possui 'repositorio_principal'.`);
        continue;
      }

      let nomeGerado = "";
      try {
        // Tenta extrair da URL
        const urlObj = new URL(repoUrl);
        const pathSegments = urlObj.pathname.split('/').filter(Boolean);
        const repoName = pathSegments[pathSegments.length - 1]; // Última parte da URL

        if (repoName) {
          // Ex: "novo-sistema-atlas" -> ["novo", "sistema", "atlas"] -> "Novo Sistema Atlas"
          nomeGerado = repoName
            .split('-')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
            .join(' ');
        } else {
          nomeGerado = repoUrl;
        }
      } catch (e) {
        // Se a URL não for válida e cair no catch, apenas copia a string
        nomeGerado = repoUrl;
      }

      console.log(`[UPDATE] ID: ${doc.id}`);
      console.log(`  URL Original: ${repoUrl}`);
      console.log(`  Nome Gerado:  ${nomeGerado}`);

      // Atualiza o batch
      batch.update(doc.ref, { nome: nomeGerado });
      batchCount++;
      totalUpdated++;

      // Se chegou a 500, commita o lote e cria um novo
      if (batchCount === 500) {
        await batch.commit();
        console.log(`Lote de 500 processado e salvo.`);
        batch = db.batch();
        batchCount = 0;
      }
    }

    // Commita o lote final (se houver sobras < 500)
    if (batchCount > 0) {
      await batch.commit();
    }

    console.log(`\nBackfill concluído com sucesso! Total de documentos atualizados: ${totalUpdated}`);

  } catch (error) {
    console.error("Erro ao executar backfill:", error);
  }
}

backfillSistemas();
