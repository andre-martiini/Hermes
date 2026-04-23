const admin = require('firebase-admin');

// Initialize Firebase Admin with default credentials
admin.initializeApp();

const db = admin.firestore();

async function run() {
  try {
    const sistemasSnapshot = await db.collection('sistemas').get();
    const unidadesSnapshot = await db.collection('unidades').get();

    const unidadesMap = new Map();
    unidadesSnapshot.forEach(doc => {
      unidadesMap.set(doc.id, doc.data().nome);
    });

    console.log("==========================================================");
    console.log("PROPOSTA DE VINCULAÇÃO - COLEÇÃO 'sistemas'");
    console.log("==========================================================\n");

    if (sistemasSnapshot.empty) {
      console.log("Nenhum documento encontrado na coleção 'sistemas'.");
      return;
    }

    sistemasSnapshot.forEach(doc => {
      const data = doc.data();
      const repoUrl = data.repositorio_principal || "";
      let nomeDerivado = "";

      if (repoUrl) {
        try {
          const urlObj = new URL(repoUrl);
          const pathSegments = urlObj.pathname.split('/').filter(Boolean);
          const repoName = pathSegments[pathSegments.length - 1] || "";

          if (repoName) {
             nomeDerivado = repoName
              .split('-')
              .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
              .join(' ');
          }
        } catch (e) {
          // Fallback se não for uma URL válida
          nomeDerivado = repoUrl;
        }
      }

      // Tenta achar na coleção de unidades para ver se o ID bate
      const nomeUnidade = unidadesMap.get(doc.id) || "Não encontrado nas unidades";

      console.log(`ID: ${doc.id}`);
      console.log(`Repositório: ${repoUrl}`);
      console.log(`Nome Derivado (Proposta): ${nomeDerivado || "Nenhum repositório"}`);
      console.log(`Nome Unidade (Se id bater): ${nomeUnidade}`);
      console.log("----------------------------------------------------------");
    });

  } catch (error) {
    console.error("Erro ao ler o Firestore:", error);
  }
}

run();
