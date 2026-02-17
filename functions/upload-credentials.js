import admin from 'firebase-admin';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Inicializa Firebase Admin
const serviceAccount = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'firebase_service_account_key.json'), 'utf8'));

admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
});

const db = admin.firestore();

async function uploadCredentials() {
    try {
        // Lê o token.json
        const tokenPath = path.join(__dirname, '..', 'token.json');

        if (!fs.existsSync(tokenPath)) {
            console.error('❌ ERRO: token.json não encontrado!');
            console.log('   Execute "python hermes_cli.py watch" uma vez para gerar o token.');
            process.exit(1);
        }

        const tokenData = JSON.parse(fs.readFileSync(tokenPath, 'utf8'));

        // Lê o credentials.json para pegar client_id e client_secret
        const credsPath = path.join(__dirname, '..', 'credentials.json');

        if (!fs.existsSync(credsPath)) {
            console.error('❌ ERRO: credentials.json não encontrado!');
            process.exit(1);
        }

        const credsData = JSON.parse(fs.readFileSync(credsPath, 'utf8'));
        const installed = credsData.installed || credsData.web;

        if (!installed) {
            console.error('❌ ERRO: Formato de credentials.json inválido!');
            process.exit(1);
        }

        // Prepara os dados para o Firestore (remove undefined)
        const firestoreData = {
            token: tokenData.token || '',
            refresh_token: tokenData.refresh_token || '',
            token_uri: tokenData.token_uri || 'https://oauth2.googleapis.com/token',
            client_id: installed.client_id || '',
            client_secret: installed.client_secret || '',
            scopes: tokenData.scopes || ['https://www.googleapis.com/auth/tasks'],
            updated_at: admin.firestore.FieldValue.serverTimestamp()
        };

        // Adiciona expiry_date apenas se existir
        if (tokenData.expiry_date) {
            firestoreData.expiry_date = tokenData.expiry_date;
        }

        // Remove campos vazios
        Object.keys(firestoreData).forEach(key => {
            if (firestoreData[key] === '' || firestoreData[key] === null) {
                delete firestoreData[key];
            }
        });

        // Salva no Firestore
        await db.collection('system').doc('google_credentials').set(firestoreData);

        console.log('');
        console.log('='.repeat(60));
        console.log('✅ CREDENCIAIS ARMAZENADAS COM SUCESSO NO FIRESTORE!');
        console.log('='.repeat(60));
        console.log('');
        console.log('📝 Próximo passo:');
        console.log('   firebase deploy --only functions');
        console.log('');
        console.log('💡 As Cloud Functions agora poderão acessar o Google Tasks');
        console.log('   automaticamente usando essas credenciais.');
        console.log('');

        process.exit(0);

    } catch (error) {
        console.error('❌ Erro ao armazenar credenciais:', error.message);
        console.error('Stack:', error.stack);
        process.exit(1);
    }
}

uploadCredentials();
