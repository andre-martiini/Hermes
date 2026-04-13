const admin = require('firebase-admin');
const fs = require('fs');

const serviceAccount = require('./firebase_service_account_key.json');
admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
});

const db = admin.firestore();

// Manually read .env.local to avoid dependency issues
let GEMINI_API_KEY = '';
try {
    const envContent = fs.readFileSync('.env.local', 'utf8');
    const match = envContent.match(/VITE_GEMINI_API_KEY\s*=\s*([^\s]+)/);
    if (match) GEMINI_API_KEY = match[1];
} catch (e) {
    console.error('Error reading .env.local:', e.message);
}

if (!GEMINI_API_KEY) {
    // Fallback to searching other common var name in the file if needed
    try {
        const envContent = fs.readFileSync('.env.local', 'utf8');
        const match = envContent.match(/GEMINI_API_KEY\s*=\s*([^\s]+)/);
        if (match) GEMINI_API_KEY = match[1];
    } catch (e) { }
}

if (!GEMINI_API_KEY) {
    console.error('GEMINI_API_KEY is missing from .env.local');
    process.exit(1);
}

async function askGemini(prompt) {
    try {
        const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key=${GEMINI_API_KEY}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ role: 'user', parts: [{ text: prompt }] }],
                generationConfig: {
                    temperature: 0.1,
                    maxOutputTokens: 100,
                }
            })
        });
        const data = await response.json();
        if (!data.candidates) {
            console.log('  ⚠️ No candidates in response:', JSON.stringify(data));
        }
        return data.candidates?.[0]?.content?.parts?.[0]?.text || '';
    } catch (error) {
        console.error('  ⚠️ Gemini error:', error.message);
        return '';
    }
}

async function migrate() {
    console.log('Fetching tasks...');
    const snapshot = await db.collection('tarefas').get();

    const tasksToUpdate = [];
    snapshot.forEach(doc => {
        const data = doc.data();
        if (data.status === 'excluído' || data.status === 'arquivado') return;
        if (data.tags && data.tags.length > 0) return; // Already tagged
        tasksToUpdate.push({ id: doc.id, ...data });
    });

    console.log(`Found ${tasksToUpdate.length} tasks needing tags.`);

    for (let i = 0; i < tasksToUpdate.length; i++) {
        const task = tasksToUpdate[i];
        console.log(`Processing ${i + 1}/${tasksToUpdate.length}: ${task.titulo}`);

        let area = task.area_tematica || task.categoria || 'Geral';
        area = area.replace('SISTEMA:', '').trim();

        const prompt = `Analise a seguinte tarefa e forneça até 5 tags curtas e altamente relevantes (1 a 2 palavras) para caracterizá-la. Use o formato de resposta estrito: [TAGS] tag1, tag2, tag3 [/TAGS].

Título: ${task.titulo}
Descrição: ${task.descricao || ''}
Área Temática: ${area}`;

        const rawResponse = await askGemini(prompt);
        const tagsMatch = rawResponse.match(/\[TAGS\]([\s\S]*?)\[\/TAGS\]/);

        let newTags = [];
        if (tagsMatch) {
            newTags = tagsMatch[1]
                .split(',')
                .map(t => t.trim().replace(/^#/, ''))
                .filter(t => t.length > 0);
        } else {
            console.log('  ⚠️ Failed to extract tags. Response:', rawResponse.replace(/\n/g, ' '));
            // Try a secondary match just in case
            newTags = rawResponse
                .split(',')
                .map(t => t.trim().replace(/^#/, '').replace(/\[TAGS\]/, '').replace(/\[\/TAGS\]/, ''))
                .filter(t => t.length > 0 && t.length < 25);
            newTags = newTags.slice(0, 5); // take max 5
        }

        if (newTags.length > 0) {
            await db.collection('tarefas').doc(task.id).update({
                tags: newTags
            });
            console.log(`  ✅ Added tags: ${newTags.join(', ')}`);
        } else {
            console.log(`  ❌ No tags generated for this task.`);
        }

        // Sleep to avoid rate limits (gemini-1.5-flash allows ~15 RPM on free tier, 1000 RPM on paid)
        // Assuming free tier to be perfectly safe, ~4 seconds per request.
        // 15 RPM = 4 seconds per req. 
        await new Promise(resolve => setTimeout(resolve, 3500));
    }

    console.log('Migration complete!');
}

migrate()
    .then(() => process.exit(0))
    .catch(err => {
        console.error(err);
        process.exit(1);
    });
