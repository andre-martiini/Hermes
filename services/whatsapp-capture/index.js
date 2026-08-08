import { Client, LocalAuth } from 'whatsapp-web.js';
import qrcode from 'qrcode-terminal';
import cron from 'node-cron';
import admin from 'firebase-admin';

// Initialize Firebase Admin (assuming default credentials in environment).
// storageBucket precisa ser resolvível para o upload de mídia funcionar — este
// worker roda fora do runtime das Cloud Functions, então o bucket padrão não é
// inferido automaticamente; configure FIREBASE_STORAGE_BUCKET se quiser mídia
// no Storage (sem isso, mensagens com mídia ainda são capturadas, só sem anexo).
if (!admin.apps.length) {
    admin.initializeApp({
        storageBucket: process.env.FIREBASE_STORAGE_BUCKET || undefined,
    });
}

const db = admin.firestore();
const FieldValue = admin.firestore.FieldValue;

const client = new Client({
    authStrategy: new LocalAuth()
});

let isClientReady = false;
let isProcessingOutbox = false;

// --- Configuração ao vivo (system/settings.whatsapp_ingest / whatsapp_auto_send_enabled) ---
// Por padrão a allowlist é vazia — o worker não captura NADA até o usuário habilitar
// explicitamente as conversas desejadas. Captura indiscriminada de todo chat/grupo é
// ruído, custo e exposição desnecessária (ver docs/okf/propostas/automacoes-canais-e-diario-pessoal.md).
let chatsAllowlist = new Set();
let allowlistLoaded = false;
let autoSendEnabled = false;

db.collection('system').doc('settings').onSnapshot((snap) => {
    const data = snap.exists ? (snap.data() || {}) : {};
    const ingestCfg = data.whatsapp_ingest || {};
    const list = Array.isArray(ingestCfg.chats_allowlist) ? ingestCfg.chats_allowlist : [];
    chatsAllowlist = new Set(list);
    allowlistLoaded = true;
    autoSendEnabled = !!data.whatsapp_auto_send_enabled;
    console.log(`[Config] Allowlist: ${chatsAllowlist.size} chat(s). Envio automático: ${autoSendEnabled}.`);
}, (err) => console.error('[Config] Falha ao observar system/settings:', err));

async function resolveDefaultTelegramChatId() {
    try {
        const snap = await db.collection('usuarios').where('telegram_chat_id', '!=', null).limit(1).get();
        if (!snap.empty) {
            const v = snap.docs[0].data().telegram_chat_id;
            if (v) return String(v);
        }
    } catch (e) { /* segue para o próximo fallback */ }
    try {
        const keysDoc = await db.collection('system').doc('api_keys').get();
        const v = keysDoc.exists ? keysDoc.data().telegram_chat_id : null;
        if (v) return String(v);
    } catch (e) { /* segue para o próximo fallback */ }
    return process.env.ALLOWED_TELEGRAM_CHAT_ID || null;
}

// Alerta mínimo via Telegram — mesmo protocolo HTTP usado pelo backend Python
// (_send_telegram_message_raw), reimplementado aqui porque este worker roda
// isolado, fora do runtime das Cloud Functions. Requer Node 18+ (fetch global).
async function sendTelegramAlert(text) {
    try {
        const keysDoc = await db.collection('system').doc('api_keys').get();
        const botToken = (keysDoc.exists && keysDoc.data().telegram_bot_token) || process.env.TELEGRAM_BOT_TOKEN;
        const chatId = await resolveDefaultTelegramChatId();
        if (!botToken || !chatId) return;
        await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chat_id: chatId, text }),
        });
    } catch (e) {
        console.error('[Telegram] Falha ao enviar alerta:', e);
    }
}

async function writeHeartbeat() {
    try {
        await db.collection('system').doc('whatsapp_worker').set({
            last_seen: admin.firestore.Timestamp.now(),
            ready: isClientReady,
        }, { merge: true });
    } catch (e) {
        console.error('[Heartbeat] Falha ao gravar:', e);
    }
}

client.on('qr', (qr) => {
    qrcode.generate(qr, { small: true });
    console.log('Scan the QR code above to authenticate.');
});

client.on('ready', () => {
    console.log('WhatsApp client is ready!');
    isClientReady = true;
    writeHeartbeat();
});

client.on('auth_failure', async (msg) => {
    console.error('Authentication failure:', msg);
    await sendTelegramAlert(`🚨 Hermes WhatsApp: falha de autenticação (${msg}). É preciso reautenticar — rode o worker no terminal e escaneie o QR novamente.`);
});

client.on('disconnected', async (reason) => {
    console.log('Client was disconnected', reason);
    isClientReady = false;
    const recoverable = reason !== 'LOGOUT';
    await sendTelegramAlert(
        `⚠️ Hermes WhatsApp: sessão desconectada (${reason}). ` +
        (recoverable ? 'Tentando reconectar automaticamente em 15s...' : 'É preciso reautenticar (escaneie o QR novamente no terminal do worker).')
    );
    if (recoverable) {
        setTimeout(() => {
            console.log('Tentando reconectar o cliente do WhatsApp...');
            client.initialize().catch((e) => console.error('Falha ao reconectar:', e));
        }, 15000);
    }
});

// Um único listener em `message_create` cobre mensagens recebidas E enviadas
// (`message.fromMe`) — antes só `message` (só recebidas) era escutado, então o
// outro lado da conversa nunca era capturado.
async function handleMessage(message) {
    try {
        const chat = await message.getChat();
        const chatId = chat.id._serialized;

        if (!allowlistLoaded || !chatsAllowlist.has(chatId)) {
            return;
        }

        const contact = await message.getContact();
        const authorName = message.fromMe
            ? 'Eu'
            : (contact.name || contact.pushname || contact.number || 'Desconhecido');

        const msgData = {
            // ID idempotente: chat + ID nativo da mensagem — antes misturava o
            // relógio de ingestão no ID, então qualquer redelivery (reconexão,
            // restart) duplicava a mensagem em vez de sobrescrever.
            id: `${chatId}_${message.id.id}`,
            wa_message_id: message.id.id,
            chat_id: chatId,
            chat_name: chat.name || (chat.isGroup ? 'Grupo' : authorName),
            is_group: !!chat.isGroup,
            author_name: authorName,
            from_me: !!message.fromMe,
            timestamp: admin.firestore.Timestamp.fromDate(new Date(message.timestamp * 1000)),
            message_type: message.type,
            content: message.body || '',
            links: (message.links || []).map((l) => (typeof l === 'string' ? l : l.link)).filter(Boolean),
            transcription_text: null,
            transcription_model: null,
            ingested_at: admin.firestore.Timestamp.now(),
        };

        if (message.hasMedia) {
            try {
                const media = await message.downloadMedia();
                if (media) {
                    const buffer = Buffer.from(media.data, 'base64');
                    msgData.media = { mimeType: media.mimetype, sizeBytes: buffer.length };
                    try {
                        const ext = (media.mimetype.split('/')[1] || 'bin').split(';')[0];
                        const storagePath = `whatsapp_media/${chatId}/${message.id.id}.${ext}`;
                        await admin.storage().bucket().file(storagePath).save(buffer, {
                            metadata: { contentType: media.mimetype },
                        });
                        msgData.media.storage_path = storagePath;
                    } catch (storageErr) {
                        console.error(`[Media] Falha ao subir para o Storage (${message.id.id}):`, storageErr.message || storageErr);
                    }
                }
            } catch (mediaErr) {
                console.error(`[Media] Falha ao baixar mídia (${message.id.id}):`, mediaErr.message || mediaErr);
            }
        }

        await db.collection('whatsapp_messages').doc(msgData.id).set(msgData, { merge: true });
        console.log(`Stored message ${msgData.id} (chat=${chatId}, fromMe=${msgData.from_me}) in whatsapp_messages.`);
    } catch (error) {
        console.error('Error handling message:', error);
    }
}

client.on('message_create', handleMessage);

client.initialize();

cron.schedule('*/5 * * * *', writeHeartbeat);

async function claimOutboxMessage(doc) {
    const lockId = `${process.pid}-${Date.now()}-${doc.id}`;
    const claimed = await db.runTransaction(async (tx) => {
        const fresh = await tx.get(doc.ref);
        if (!fresh.exists) {
            return null;
        }

        const data = fresh.data();
        if (data.status !== 'pending') {
            return null;
        }

        if (!data.to_number || !data.content) {
            tx.update(doc.ref, {
                status: 'failed',
                error_message: 'Missing to_number or content',
                failed_at: admin.firestore.Timestamp.now(),
                updated_at: admin.firestore.Timestamp.now()
            });
            return null;
        }

        tx.update(doc.ref, {
            status: 'sending',
            lock_id: lockId,
            locked_at: admin.firestore.Timestamp.now(),
            attempts: FieldValue.increment(1),
            updated_at: admin.firestore.Timestamp.now()
        });

        return { ...data, lockId };
    });

    return claimed;
}

// ACTIVE MODULE: Outbox checking cron job.
// Só reivindica mensagens quando system/settings.whatsapp_auto_send_enabled é true —
// antes este cron e a Cloud Function dispatch_scheduled_whatsapp_messages (que manda
// um link wa.me pelo Telegram em vez de enviar de verdade) disputavam os mesmos docs
// 'pending' sem nenhuma coordenação; a CF quase sempre "roubava" o doc primeiro,
// então o envio automático raramente acontecia de fato.
cron.schedule('* * * * *', async () => {
    if (!autoSendEnabled) {
        return;
    }
    if (!isClientReady) {
        console.log('Skipping cron tick: WhatsApp client not ready.');
        return;
    }
    if (isProcessingOutbox) {
        console.log('Skipping cron tick: previous outbox run still active.');
        return;
    }

    isProcessingOutbox = true;
    try {
        const now = admin.firestore.Timestamp.now();

        // Fetch pending messages whose scheduled time has passed or is now
        const snapshot = await db.collection('whatsapp_outbox')
            .where('status', '==', 'pending')
            .where('scheduled_for', '<=', now)
            .limit(25)
            .get();

        if (snapshot.empty) {
            return;
        }

        for (const doc of snapshot.docs) {
            const data = await claimOutboxMessage(doc);
            if (!data) {
                continue;
            }

            const toNumber = data.to_number;
            const content = data.content;

            try {
                // Ensure the number is formatted correctly (e.g. 5527999999999@c.us)
                const formattedNumber = toNumber.includes('@c.us') || toNumber.includes('@g.us') ? toNumber : `${toNumber}@c.us`;

                await client.sendMessage(formattedNumber, content);

                // Update status to sent
                await doc.ref.update({
                    status: 'sent',
                    sent_at: admin.firestore.Timestamp.now(),
                    updated_at: admin.firestore.Timestamp.now()
                });
                console.log(`Message sent to ${toNumber}`);

            } catch (error) {
                // Log failure
                console.error(`Failed to send message to ${toNumber}:`, error);
                await doc.ref.update({
                    status: 'failed',
                    error_message: error.message || 'Unknown error',
                    failed_at: admin.firestore.Timestamp.now(),
                    updated_at: admin.firestore.Timestamp.now()
                });
            }
        }
    } catch (err) {
        console.error('Error during outbox processing cron tick:', err);
    } finally {
        isProcessingOutbox = false;
    }
});
