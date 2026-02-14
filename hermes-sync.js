
import admin from 'firebase-admin';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const KEY_PATH = path.join(__dirname, 'firebase_service_account_key.json');
const JSON_FILE = path.join(__dirname, 'hermes_sync.json');

// Inicialização segura
if (!fs.existsSync(KEY_PATH)) {
    console.error(`ERRO: Chave '${KEY_PATH}' não encontrada.`);
    process.exit(1);
}

const serviceAccount = JSON.parse(fs.readFileSync(KEY_PATH, 'utf8'));

admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
});

const db = admin.firestore();
let lastSyncState = null;
let isWritingToFile = false;
let isWritingToCloud = false;

// Função para exportar tudo para o JSON
async function exportToLocal() {
    if (isWritingToCloud) return; // Evita loop
    
    isWritingToFile = true;
    try {
        const collections = ['tarefas', 'atividades', 'unidades', 'afastamentos'];
        const data = {};

        for (const colName of collections) {
            const snapshot = await db.collection(colName).get();
            data[colName] = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
        }

        const jsonContent = JSON.stringify(data, null, 2);
        
        // Só grava se houver mudança real
        if (jsonContent !== lastSyncState) {
            fs.writeFileSync(JSON_FILE, jsonContent);
            lastSyncState = jsonContent;
            console.log(`[${new Date().toLocaleTimeString()}] JSON Atualizado (Mirror do Banco)`);
        }
    } catch (err) {
        console.error("Erro ao exportar:", err);
    } finally {
        isWritingToFile = false;
    }
}

// Função para importar do JSON para o Cloud
async function importToCloud() {
    if (isWritingToFile) return;
    
    const content = fs.readFileSync(JSON_FILE, 'utf8');
    if (content === lastSyncState) return;

    isWritingToCloud = true;
    console.log(`[${new Date().toLocaleTimeString()}] Alteração local detectada. Sincronizando com Cloud...`);
    
    try {
        const data = JSON.parse(content);
        lastSyncState = content;

        for (const [colName, docs] of Object.entries(data)) {
            for (const docData of docs) {
                const { id, ...payload } = docData;
                if (id) {
                    await db.collection(colName).doc(id).set(payload, { merge: true });
                } else {
                    await db.collection(colName).add(payload);
                }
            }
        }
        console.log("Sincronização Cloud concluída.");
    } catch (err) {
        console.error("Erro ao sincronizar com Cloud:", err);
    } finally {
        isWritingToCloud = false;
        // Após subir, forçamos um export para garantir IDs novos e consistência
        await exportToLocal();
    }
}

// Listeners Real-time do Firebase
const collectionsToWatch = ['tarefas', 'atividades', 'unidades'];
collectionsToWatch.forEach(col => {
    db.collection(col).onSnapshot(() => {
        if (!isWritingToCloud) {
            exportToLocal();
        }
    }, err => console.error(`Erro no listener ${col}:`, err));
});

// Watcher do Arquivo Local
fs.watch(JSON_FILE, (event) => {
    if (event === 'change' && !isWritingToFile) {
        // Debounce simples para evitar multiplos triggers
        setTimeout(importToCloud, 100);
    }
});

console.log("-----------------------------------------");
console.log("HERMES SYNC DAEMON INICIADO");
console.log("Monitorando Firestore e 'hermes_sync.json'...");
console.log("-----------------------------------------");

// Export inicial
exportToLocal();
