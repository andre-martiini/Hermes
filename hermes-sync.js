
import { initializeApp } from "firebase/app";
import { 
    getFirestore, 
    collection, 
    onSnapshot, 
    getDocs, 
    setDoc, 
    doc,
    addDoc
} from "firebase/firestore";
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const JSON_FILE = path.join(__dirname, 'hermes_full_database.json');

// Configuração extraída do firebase.ts
const firebaseConfig = {
  apiKey: "AIzaSyCc00Qqsa7Zgfx9NZkLoPj_gvXcuMczuxk",
  authDomain: "gestao-hermes.firebaseapp.com",
  projectId: "gestao-hermes",
  storageBucket: "gestao-hermes.firebasestorage.app",
  messagingSenderId: "1003307358410",
  appId: "1:1003307358410:web:c0726a4de406584fad7c33",
  measurementId: "G-ZKX16ZRTDN"
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

let lastSyncState = null;
let isWritingToFile = false;
let isWritingToCloud = false;
let watchTimeout = null;

// Helpers de Git
function gitPull() {
    try {
        console.log("[Git] Verificando atualizações no GitHub...");
        execSync('git pull origin main', { stdio: 'ignore' });
    } catch (e) {
        console.warn("[Git] Aviso: Falha no Pull GitHub (pode ser ausência de internet ou conflito).");
    }
}

function gitPush() {
    try {
        console.log("[Git] Registrando alterações no repositório...");
        execSync(`git add hermes_full_database.json`, { stdio: 'ignore' });
        execSync('git commit -m "Real-time Sync: Update Database JSON"', { stdio: 'ignore' });
        execSync('git push origin main', { stdio: 'ignore' });
        console.log("[Git] Sincronizado com GitHub.");
    } catch (e) {
        // Silencioso se não houver mudanças
    }
}

// Exportar tudo para o JSON
async function exportToLocal() {
    if (isWritingToCloud) return;
    
    isWritingToFile = true;
    try {
        const collections = ['tarefas', 'atividades', 'atividades_pgc', 'unidades', 'afastamentos'];
        const data = {};

        for (const colName of collections) {
            const snapshot = await getDocs(collection(db, colName));
            data[colName] = snapshot.docs.map(d => ({ id: d.id, ...d.data() }));
            console.log(`[Sync] Lendo coleção: ${colName} (${data[colName].length} itens)`);
        }

        const jsonContent = JSON.stringify(data, null, 2);
        
        if (jsonContent !== lastSyncState) {
            fs.writeFileSync(JSON_FILE, jsonContent);
            lastSyncState = jsonContent;
            console.log(`[${new Date().toLocaleTimeString()}] Banco de Dados JSON Atualizado.`);
            gitPush();
        }
    } catch (err) {
        console.error("Erro ao exportar do Firestore:", err);
    } finally {
        isWritingToFile = false;
    }
}

// Importar do JSON para o Cloud (quando o bot altera o arquivo)
async function importToCloud() {
    if (isWritingToFile) return;
    
    gitPull();

    if (!fs.existsSync(JSON_FILE)) return;
    const content = fs.readFileSync(JSON_FILE, 'utf8');
    if (!content || content === lastSyncState) return;

    isWritingToCloud = true;
    console.log(`[${new Date().toLocaleTimeString()}] Alteração local detectada. Sincronizando com Firestore...`);
    
    try {
        const data = JSON.parse(content);
        lastSyncState = content;

        for (const [colName, docs] of Object.entries(data)) {
            if (!Array.isArray(docs)) continue;
            for (const docData of docs) {
                const { id, ...payload } = docData;
                if (id && id.length > 5) { 
                    await setDoc(doc(db, colName, id), payload, { merge: true });
                } else {
                    await addDoc(collection(db, colName), payload);
                }
            }
        }
        console.log("Firestore Sincronizada com Sucesso.");
    } catch (err) {
        console.error("Erro ao sincronizar Cloud:", err);
    } finally {
        isWritingToCloud = false;
        await exportToLocal();
    }
}

// Configurar Listeners em Tempo Real
const collectionsToWatch = ['tarefas', 'atividades', 'atividades_pgc', 'unidades', 'afastamentos'];
collectionsToWatch.forEach(colName => {
    onSnapshot(collection(db, colName), (snapshot) => {
        // Se a mudança não partiu deste script de importação, exportamos
        if (!isWritingToCloud) {
            console.log(`[Listener] Mudança detectada na coleção: ${colName}`);
            exportToLocal();
        }
    });
});

// Assistir o arquivo JSON para mudanças manuais (do Bot/Git)
fs.watch(JSON_FILE, (event) => {
    if (event === 'change' && !isWritingToFile) {
        // Debounce simples para evitar múltiplas leituras
        if (watchTimeout) clearTimeout(watchTimeout);
        watchTimeout = setTimeout(() => {
            importToCloud();
        }, 500);
    }
});

console.log("=========================================");
console.log("   HERMES REAL-TIME SYNC SYSTEM V2       ");
console.log("   Firestore Real-time <=> JSON Master   ");
console.log("=========================================");

// Inicialização
gitPull();
exportToLocal();

// Pull periódico para garantir sincronia com alterações remotas no Git
setInterval(gitPull, 10 * 60 * 1000); 
