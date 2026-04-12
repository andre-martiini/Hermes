
import { db } from './firebase';
import { collection, getDocs, limit, query } from 'firebase/firestore';

async function debugEdges() {
    try {
        const q = query(collection(db, 'knowledge_edges'), limit(1));
        const snapshot = await getDocs(q);
        if (snapshot.empty) {
            console.log("Nenhuma aresta encontrada em 'knowledge_edges'");
            return;
        }
        const doc = snapshot.docs[0];
        console.log("ID da aresta:", doc.id);
        console.log("Dados da aresta:", JSON.stringify(doc.data(), null, 2));
    } catch (e) {
        console.error("Erro ao ler arestas:", e);
    }
}

debugEdges();
