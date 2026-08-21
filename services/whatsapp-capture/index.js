import pkg from 'whatsapp-web.js';
const { Client, LocalAuth } = pkg;
import qrcode from 'qrcode-terminal';
import qrcodeImage from 'qrcode';
import cron from 'node-cron';
import admin from 'firebase-admin';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const QR_IMAGE_PATH = path.join(__dirname, 'qr-code.png');
const AUTH_DIR = path.join(__dirname, '.wwebjs_auth');
const AUTH_RESET_MARKER = path.join(__dirname, '.needs-auth-reset');

// Um LOGOUT pode deixar a sessão pela metade: o Chromium ainda segura arquivos
// do perfil quando a LocalAuth tenta apagá-la (EBUSY). O marker é gravado no
// LOGOUT e consumido aqui, antes do Chromium subir — o único momento em que
// nenhum arquivo do perfil está travado e o rm consegue concluir.
if (fs.existsSync(AUTH_RESET_MARKER)) {
    try {
        fs.rmSync(AUTH_DIR, { recursive: true, force: true, maxRetries: 10, retryDelay: 500 });
        fs.rmSync(AUTH_RESET_MARKER, { force: true });
        console.log('[Auth] Sessão anterior removida (reset pendente de um LOGOUT).');
    } catch (e) {
        console.error('[Auth] Falha ao remover sessão antiga; o login pode exigir novo QR mesmo assim:', e);
    }
}

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
    authStrategy: new LocalAuth({ dataPath: AUTH_DIR, rmMaxRetries: 8 })
});

let isClientReady = false;
let isProcessingOutbox = false;
let isSyncingChats = false;
let lastChatsSyncMs = 0;
const CHATS_SYNC_INTERVAL_MS = 6 * 60 * 60 * 1000; // 6h
const CHATS_READY_DELAY_MS = 60_000; // 60s

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

async function syncChatRegistry() {
    if (!isClientReady) {
        console.log('[Chats] Pulando sincronização: cliente WhatsApp não está pronto.');
        return;
    }
    if (isSyncingChats) {
        console.log('[Chats] Pulando sincronização: outra sincronização já está em andamento.');
        return;
    }

    isSyncingChats = true;
    try {
        console.log('[Chats] Sincronizando registro de chats do WhatsApp...');
        const rawChats = await client.getChats();
        if (!Array.isArray(rawChats)) {
            console.warn('[Chats] client.getChats() não retornou array.');
            return;
        }

        const BATCH_SIZE = 450;
        let batch = db.batch();
        let countInBatch = 0;
        let totalSaved = 0;

        for (const chat of rawChats) {
            try {
                const chatId = chat.id?._serialized || (typeof chat.id === 'string' ? chat.id : null);
                if (!chatId) continue;

                const isGroup = !!chat.isGroup;
                const chatName = chat.name || chatId;
                let lastActivityTs = null;
                if (chat.timestamp) {
                    lastActivityTs = admin.firestore.Timestamp.fromDate(new Date(chat.timestamp * 1000));
                }

                const docRef = db.collection('whatsapp_chats').doc(chatId);
                const data = {
                    chat_id: chatId,
                    chat_name: chatName,
                    is_group: isGroup,
                    last_activity_ts: lastActivityTs,
                    last_synced_at: admin.firestore.FieldValue.serverTimestamp(),
                };

                batch.set(docRef, data, { merge: true });
                countInBatch++;
                totalSaved++;

                if (countInBatch >= BATCH_SIZE) {
                    await batch.commit();
                    batch = db.batch();
                    countInBatch = 0;
                }
            } catch (itemErr) {
                console.error('[Chats] Falha ao processar chat individual:', itemErr);
            }
        }

        if (countInBatch > 0) {
            await batch.commit();
        }

        lastChatsSyncMs = Date.now();
        console.log(`[Chats] Registro sincronizado: ${totalSaved} chat(s) salvos/atualizados.`);
    } catch (err) {
        console.error('[Chats] Erro ao sincronizar registro de chats:', err);
    } finally {
        isSyncingChats = false;
    }
}

client.on('qr', (qr) => {
    qrcode.generate(qr, { small: true });
    console.log('Scan the QR code above to authenticate.');
    // Alguns terminais (ex.: painéis embutidos de IDE/CLI) distorcem a arte ASCII
    // acima — largura fixa quebra o QR em linhas erradas. Como fallback, salva
    // sempre a mesma imagem PNG para abrir e escanear diretamente.
    qrcodeImage.toFile(QR_IMAGE_PATH, qr, { width: 400 }, (err) => {
        if (err) {
            console.error('[QR] Falha ao salvar imagem PNG:', err);
        } else {
            console.log(`[QR] Imagem salva em ${QR_IMAGE_PATH} — abra o arquivo se o QR do terminal não escanear.`);
        }
    });
});

client.on('ready', async () => {
    console.log('WhatsApp client is ready!');
    isClientReady = true;
    writeHeartbeat();
    setTimeout(syncChatRegistry, CHATS_READY_DELAY_MS);
});

client.on('auth_failure', async (msg) => {
    console.error('Authentication failure:', msg);
    await sendTelegramAlert(`🚨 Hermes WhatsApp: falha de autenticação (${msg}). É preciso reautenticar — rode o worker no terminal e escaneie o QR novamente.`);
});

client.on('disconnected', async (reason) => {
    console.log('Client was disconnected', reason);
    isClientReady = false;
    const recoverable = reason !== 'LOGOUT';
    if (!recoverable) {
        // O rm feito pela LocalAuth durante o LOGOUT pode falhar com o Chromium
        // ainda aberto; o marker garante que o próximo boot parta de sessão zerada.
        try {
            fs.writeFileSync(AUTH_RESET_MARKER, new Date().toISOString());
        } catch (e) {
            console.error('[Auth] Falha ao gravar marker de reset:', e);
        }
    }
    await sendTelegramAlert(
        `⚠️ Hermes WhatsApp: sessão desconectada (${reason}). ` +
        (recoverable ? 'Tentando reconectar automaticamente em 15s...' : 'É preciso reautenticar — um novo QR será gerado e salvo em qr-code.png na pasta do worker.')
    );
    if (recoverable) {
        setTimeout(() => {
            console.log('Tentando reconectar o cliente do WhatsApp...');
            client.initialize().catch((e) => console.error('Falha ao reconectar:', e));
        }, 15000);
    }
});

async function resolveChatContext(message) {
    let chat = null;
    let chatId = null;
    let isGroup = false;

    try {
        chat = await message.getChat();
        if (chat && chat.id) {
            chatId = chat.id._serialized;
            isGroup = !!chat.isGroup;
        }
    } catch (chatErr) {
        console.warn('[Message] Falha ao obter chat via getChat():', chatErr.message || chatErr);
    }

    // Fallback para chatId se getChat() falhar
    if (!chatId) {
        const rawTarget = message.fromMe ? message.to : message.from;
        if (rawTarget) {
            chatId = typeof rawTarget === 'object' && rawTarget._serialized ? rawTarget._serialized : String(rawTarget);
        }
        if (chatId) {
            isGroup = chatId.endsWith('@g.us');
        }
    }

    return { chat, chatId, isGroup };
}

// Grava uma mensagem em whatsapp_messages — usado tanto pela captura ao vivo
// (handleMessage) quanto pelo backfill sob demanda (backfillChatHistory).
async function persistMessage(message, chat, chatId, isGroup) {
    let authorName = 'Desconhecido';
    if (message.fromMe) {
        authorName = 'Eu';
    } else {
        try {
            const contact = await message.getContact();
            if (contact) {
                authorName = contact.name || contact.pushname || contact.number || 'Desconhecido';
            }
        } catch (contactErr) {
            authorName = message._data?.notifyName || message.author || message.from || 'Desconhecido';
        }
    }

    const chatTitle = chat?.name || (isGroup ? 'Grupo' : authorName);

    const msgData = {
        // ID idempotente: chat + ID nativo da mensagem — antes misturava o
        // relógio de ingestão no ID, então qualquer redelivery (reconexão,
        // restart) duplicava a mensagem em vez de sobrescrever.
        id: `${chatId}_${message.id.id}`,
        wa_message_id: message.id.id,
        chat_id: chatId,
        chat_name: chatTitle,
        is_group: isGroup,
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
    return msgData.id;
}

// Um único listener em `message_create` cobre mensagens recebidas E enviadas
// (`message.fromMe`) — antes só `message` (só recebidas) era escutado, então o
// outro lado da conversa nunca era capturado.
async function handleMessage(message) {
    try {
        const { chat, chatId, isGroup } = await resolveChatContext(message);

        if (!chatId) {
            console.warn('[Message] Não foi possível determinar o chatId da mensagem:', message.id?.id);
            return;
        }

        if (!allowlistLoaded || !chatsAllowlist.has(chatId)) {
            return;
        }

        const storedId = await persistMessage(message, chat, chatId, isGroup);
        console.log(`Stored message ${storedId} (chat=${chatId}) in whatsapp_messages.`);
    } catch (error) {
        console.error('Error handling message:', error);
    }
}

client.on('message_create', handleMessage);

// --- Sync sob demanda (backfill de histórico) ---
// A captura ao vivo (handleMessage) só grava o que chega enquanto o worker está
// rodando — sem histórico anterior. Quando o front abre um chat, grava um pedido em
// whatsapp_sync_requests/{chat_id}; aqui puxamos as últimas mensagens via
// chat.fetchMessages() (API do próprio WhatsApp Web, não passa pelo listener ao
// vivo) e completamos só o que ainda não está em whatsapp_messages — mensagens já
// conhecidas não são regravadas, então mídia já baixada não é rebaixada a cada sync.
const DEFAULT_SYNC_LIMIT = 100;
const MAX_SYNC_LIMIT = 300;
const processingSyncRequests = new Set();

async function backfillChatHistory(chatId, limitCount) {
    const chat = await client.getChatById(chatId);
    const isGroup = !!chat.isGroup;
    const fetched = await chat.fetchMessages({ limit: limitCount });

    if (!Array.isArray(fetched) || fetched.length === 0) {
        return { fetched: 0, stored: 0 };
    }

    const refs = fetched.map((m) => db.collection('whatsapp_messages').doc(`${chatId}_${m.id.id}`));
    const snaps = await db.getAll(...refs);
    const existingIds = new Set(snaps.filter((snap) => snap.exists).map((snap) => snap.id));

    let stored = 0;
    for (const message of fetched) {
        const id = `${chatId}_${message.id.id}`;
        if (existingIds.has(id)) continue;
        try {
            await persistMessage(message, chat, chatId, isGroup);
            stored++;
        } catch (persistErr) {
            console.error(`[Sync] Falha ao gravar mensagem ${id} do backfill:`, persistErr.message || persistErr);
        }
    }

    return { fetched: fetched.length, stored };
}

async function handleSyncRequest(requestId, data) {
    if (processingSyncRequests.has(requestId)) return;
    processingSyncRequests.add(requestId);

    const ref = db.collection('whatsapp_sync_requests').doc(requestId);
    const chatId = data.chat_id || requestId;
    const limitCount = Math.min(Math.max(Number(data.limit) || DEFAULT_SYNC_LIMIT, 1), MAX_SYNC_LIMIT);

    try {
        if (!isClientReady) {
            await ref.set({ status: 'error', error: 'worker_not_ready', updated_at: admin.firestore.Timestamp.now() }, { merge: true });
            return;
        }
        // Mesma allowlist da captura ao vivo — não busca histórico de chat fora dela.
        if (!allowlistLoaded || !chatsAllowlist.has(chatId)) {
            await ref.set({ status: 'skipped', error: 'chat_not_monitored', updated_at: admin.firestore.Timestamp.now() }, { merge: true });
            return;
        }

        await ref.set({ status: 'processing', updated_at: admin.firestore.Timestamp.now() }, { merge: true });
        const { fetched, stored } = await backfillChatHistory(chatId, limitCount);
        await ref.set({
            status: 'done',
            fetched_count: fetched,
            stored_count: stored,
            updated_at: admin.firestore.Timestamp.now(),
        }, { merge: true });
        console.log(`[Sync] Chat ${chatId}: ${stored} nova(s) mensagem(ns) de ${fetched} verificada(s).`);
    } catch (err) {
        console.error(`[Sync] Falha ao sincronizar chat ${chatId}:`, err.message || err);
        await ref.set({ status: 'error', error: String(err.message || err), updated_at: admin.firestore.Timestamp.now() }, { merge: true }).catch(() => {});
    } finally {
        processingSyncRequests.delete(requestId);
    }
}

db.collection('whatsapp_sync_requests')
    .where('status', '==', 'pending')
    .onSnapshot((snap) => {
        snap.docChanges().forEach((change) => {
            if (change.type === 'added' || change.type === 'modified') {
                handleSyncRequest(change.doc.id, change.doc.data());
            }
        });
    }, (err) => console.error('[Sync] Falha ao observar whatsapp_sync_requests:', err));

client.initialize();

cron.schedule('*/5 * * * *', async () => {
    await writeHeartbeat();
    if (isClientReady && (Date.now() - lastChatsSyncMs >= CHATS_SYNC_INTERVAL_MS)) {
        syncChatRegistry().catch((e) => console.error('[Chats] Falha no cron de sincronização de chats:', e));
    }
});

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

// Rede de segurança: erros não tratados (ex.: rejeição dentro de handlers do
// puppeteer/whatsapp-web.js) derrubariam o processo inteiro — e não há
// supervisor para reerguê-lo fora do logon. Melhor logar, alertar e seguir vivo.
let lastFatalAlertMs = 0;
function reportFatal(kind, err) {
    console.error(`[${kind}]`, err);
    const now = Date.now();
    if (now - lastFatalAlertMs < 10 * 60 * 1000) return; // no máximo 1 alerta a cada 10min
    lastFatalAlertMs = now;
    sendTelegramAlert(
        `🚨 Hermes WhatsApp worker: erro não tratado (${kind}): ${err?.message || err}. ` +
        'O worker continua rodando; se a captura parar, reinicie-o.'
    );
}
process.on('unhandledRejection', (reason) => reportFatal('unhandledRejection', reason));
process.on('uncaughtException', (err) => reportFatal('uncaughtException', err));
