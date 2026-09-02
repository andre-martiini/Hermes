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
    authStrategy: new LocalAuth({ dataPath: AUTH_DIR, rmMaxRetries: 8 }),
    // Mídias grandes estouravam o protocolTimeout padrão (180s) do puppeteer no
    // downloadMedia ("Runtime.callFunctionOn timed out") — visto em produção.
    puppeteer: { protocolTimeout: 300000 },
});

let isClientReady = false;
let isProcessingOutbox = false;
let isSyncingChats = false;
let lastChatsSyncMs = 0;
const CHATS_SYNC_INTERVAL_MS = 6 * 60 * 60 * 1000; // 6h
// Recuperação com `capturar_todos`: só chats mexidos nesta janela (ou com não
// lidas) entram, e no máximo este tanto por passagem.
const RECOVERY_JANELA_DIAS = 7;
const RECOVERY_MAX_CHATS = 150;
// Resolução de telefone por chat: quantos contatos novos resolver por sincronização.
// Cada um é uma chamada ao WhatsApp Web, então o primeiro passe fatia o trabalho
// e os seguintes só pegam o que apareceu depois.
const CONTATOS_POR_SYNC = 120;
const CHATS_READY_DELAY_MS = 60_000; // 60s

// --- Configuração ao vivo (system/settings.whatsapp_ingest / whatsapp_auto_send_enabled) ---
//
// Duas decisões diferentes, que até 27/08/2026 eram a mesma:
//
//   capturar_todos    o worker guarda TODA conversa, sem lista
//   chats_allowlist   quais conversas o agente (MCP) pode LER
//
// Elas viviam no mesmo campo, e isso escondia uma consequência: ligar a captura
// em todos os contatos daria ao Claude, de uma vez, leitura das 450 conversas
// individuais. Guardar é um risco; deixar um agente ler é outro.
//
// Com `capturar_todos` ligado, a allowlist deixa de governar a captura e passa a
// significar só "o agente pode ler" — que é o que a Caixa de Entrada mostra como
// conversa monitorada. Desligado, o comportamento é o de antes: allowlist vazia
// captura NADA, porque captura indiscriminada é ruído, custo e exposição
// (ver docs/okf/propostas/automacoes-canais-e-diario-pessoal.md).
let chatsAllowlist = new Set();
let allowlistLoaded = false;
let capturarTodos = false;
let autoSendEnabled = false;

db.collection('system').doc('settings').onSnapshot((snap) => {
    const data = snap.exists ? (snap.data() || {}) : {};
    const ingestCfg = data.whatsapp_ingest || {};
    const list = Array.isArray(ingestCfg.chats_allowlist) ? ingestCfg.chats_allowlist : [];
    chatsAllowlist = new Set(list);
    capturarTodos = !!ingestCfg.capturar_todos;
    allowlistLoaded = true;
    autoSendEnabled = !!data.whatsapp_auto_send_enabled;
    console.log(`[Config] Captura total: ${capturarTodos}. Leitura pelo agente: `
        + `${chatsAllowlist.size} chat(s). Envio automático: ${autoSendEnabled}.`);
}, (err) => console.error('[Config] Falha ao observar system/settings:', err));

/** Se este chat deve ser capturado. Fecha por omissão enquanto a config não chega. */
function deveCapturar(chatId) {
    if (!allowlistLoaded) return false;
    return capturarTodos || chatsAllowlist.has(chatId);
}

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

/**
 * Telefone real de um chat individual.
 *
 * `chat.getContact().number` NAO serve para `@lid`: devolve os digitos do
 * proprio lid. Foi o que aconteceu na primeira tentativa — 120 chats gravaram
 * `contact_number: 102100113604695` para o chat `102100113604695@lid`, um
 * numero que nao casa com telefone nenhum e que, pior, poderia colidir nos
 * ultimos 8 digitos com o telefone de outra pessoa.
 *
 * O mapeamento lid -> telefone vive na propria pagina do WhatsApp Web:
 * `WAWebApiContact.getPhoneNumber(wid)`. A biblioteca ja o expoe injetado como
 * `WWebJS.enforceLidAndPnRetrieval`, que ainda consulta o servidor quando o
 * mapeamento nao esta em cache — e por isso a resolucao tem teto por passagem.
 */
async function telefoneDoChat(chatId, chat) {
    const soDigitos = (v) => String(v || '').replace(/[^0-9]/g, '');
    const lidDigits = chatId.endsWith('@lid') ? soDigitos(chatId.split('@')[0]) : '';

    try {
        const phone = await client.pupPage.evaluate(async (id) => {
            try {
                const r = await window.WWebJS.enforceLidAndPnRetrieval(id);
                return r?.phone?.user || null;
            } catch (e) {
                return null;
            }
        }, chatId);
        const num = soDigitos(phone);
        // Se voltou o proprio lid, nao resolveu nada: gravar seria pior que
        // deixar em branco, porque um numero errado casa com alguem.
        if (num.length >= 8 && num !== lidDigits) return num;
    } catch (e) {
        // pupPage indisponivel (reconectando): tenta o caminho classico abaixo.
    }

    try {
        const contato = await chat.getContact();
        const num = soDigitos(contato?.number);
        if (num.length >= 8 && num !== lidDigits) return num;
    } catch (e) {
        // Contato apagado ou sem numero visivel.
    }
    return null;
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

        // Quem já tem telefone resolvido não é perguntado de novo. Sem isto,
        // seriam ~450 chamadas ao WhatsApp Web a cada 6h para redescobrir o
        // mesmo número.
        const jaComNumero = new Set();
        try {
            const existentes = await db.collection('whatsapp_chats')
                .where('contact_number', '!=', null).select().get();
            existentes.forEach((d) => jaComNumero.add(d.id));
        } catch (e) {
            console.warn('[Chats] Não foi possível listar chats já resolvidos:', e.message || e);
        }
        let resolvidos = 0;

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

                // O telefone precisa vir daqui porque o chat_id deixou de tê-lo:
                // o WhatsApp migrou os contatos individuais para `@lid`, um
                // identificador que não deriva do número. Sem isto,
                // `linkWhatsappContacts` compara os últimos 8 dígitos de um ID
                // opaco com um telefone de verdade e não casa nada — na medição
                // de 27/08/2026, 450 chats `@lid` contra 0 vínculos possíveis.
                if (!isGroup && !jaComNumero.has(chatId) && resolvidos < CONTATOS_POR_SYNC) {
                    const numero = await telefoneDoChat(chatId, chat);
                    if (numero) {
                        data.contact_number = numero;
                        data.contact_number_resolved_at =
                            admin.firestore.FieldValue.serverTimestamp();
                        resolvidos++;
                    }
                }

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
        console.log(`[Chats] Registro sincronizado: ${totalSaved} chat(s) salvos/atualizados`
            + `, ${resolvidos} telefone(s) resolvido(s).`);
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
    // Recuperação retroativa: o que chegou com o worker desligado não passa pelo
    // message_create; ao ficar pronto, completamos o buraco a partir do histórico.
    setTimeout(recoverMissedMessages, RECOVERY_READY_DELAY_MS);
    setTimeout(() => {
        repairMissingMedia().catch((e) => console.error('[MediaRepair] Falha na varredura pós-ready:', e));
    }, MEDIA_REPAIR_READY_DELAY_MS);
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

// Baixa a mídia de uma mensagem e sobe para o Storage, com retry no upload —
// falha transitória de rede/DNS (ENOTFOUND www.googleapis.com, visto em produção
// em 21/08 custando 5 mídias) não pode custar o arquivo, pois a mensagem só é
// capturada uma vez. Retorna { mimeType, sizeBytes, storage_path? } ou null se
// o download falhar.
const STORAGE_UPLOAD_ATTEMPTS = 3;

async function captureMedia(message, chatId) {
    let media = null;
    try {
        media = await message.downloadMedia();
    } catch (mediaErr) {
        console.error(`[Media] Falha ao baixar mídia (${message.id.id}):`, mediaErr.message || mediaErr);
        return null;
    }
    if (!media || !media.data) {
        return null;
    }
    const buffer = Buffer.from(media.data, 'base64');
    // mimetype pode vir undefined — sem o fallback, o undefined quebrava o
    // upload no split() E invalidava o documento inteiro no Firestore ("Cannot
    // use undefined as a Firestore value"), perdendo a mensagem por completo.
    const mimeType = media.mimetype || 'application/octet-stream';
    const result = { mimeType, sizeBytes: buffer.length };
    const ext = (mimeType.split('/')[1] || 'bin').split(';')[0];
    const storagePath = `whatsapp_media/${chatId}/${message.id.id}.${ext}`;
    for (let attempt = 1; attempt <= STORAGE_UPLOAD_ATTEMPTS; attempt++) {
        try {
            await admin.storage().bucket().file(storagePath).save(buffer, {
                metadata: { contentType: mimeType },
            });
            result.storage_path = storagePath;
            break;
        } catch (storageErr) {
            console.error(`[Media] Falha ao subir para o Storage (${message.id.id}, tentativa ${attempt}/${STORAGE_UPLOAD_ATTEMPTS}):`, storageErr.message || storageErr);
            if (attempt < STORAGE_UPLOAD_ATTEMPTS) {
                await new Promise((resolve) => setTimeout(resolve, attempt * 5000));
            }
        }
    }
    return result;
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
    // Metadados de contexto de grupo para a caixa de respostas pendentes.
    const mentionedIds = Array.isArray(message.mentionedIds)
        ? message.mentionedIds.map((id) => String(id?._serialized || id)).filter(Boolean)
        : [];
    const ownWid = String(client?.info?.wid?._serialized || '');
    const rawQuoted = message?._data?.quotedMsg || message?._data?.quotedMessage || {};
    const rawQuotedId = message?._data?.quotedStanzaID || message?._data?.quotedMsgId
        || rawQuoted?.id?._serialized || null;
    let rawQuotedFromMe = rawQuoted?.fromMe ?? rawQuoted?.id?.fromMe;
    // No whatsapp-web.js normal, `_data.quotedStanzaID` traz só o identificador
    // da citação — o objeto da mensagem citada não vem em `quotedMsg`. Para não
    // descartar respostas diretas ao André, busque o remetente apenas quando há
    // citação e o payload ainda não o informou. Isto roda na captura da mensagem
    // nova, nunca como reprocessamento do histórico.
    if (rawQuotedId && typeof rawQuotedFromMe !== 'boolean'
        && typeof message.getQuotedMessage === 'function') {
        try {
            const quoted = await message.getQuotedMessage();
            rawQuotedFromMe = quoted?.fromMe ?? quoted?.id?.fromMe;
        } catch (quotedErr) {
            console.warn(`[Message] Não foi possível resolver mensagem citada ${rawQuotedId}:`, quotedErr.message || quotedErr);
        }
    }

    const msgData = {
        // ID idempotente: chat + ID nativo da mensagem — antes misturava o
        // relógio de ingestão no ID, então qualquer redelivery (reconexão,
        // restart) duplicava a mensagem em vez de sobrescrever.
        id: `${chatId}_${message.id.id}`,
        wa_message_id: message.id.id,
        // ID serializado completo (fromMe_chatId_id[_participante]) — necessário
        // para reencontrar a mensagem via getMessageById no reparo de mídia.
        wa_serialized_id: message.id._serialized || null,
        chat_id: chatId,
        chat_name: chatTitle,
        is_group: isGroup,
        author_name: authorName,
        from_me: !!message.fromMe,
        timestamp: admin.firestore.Timestamp.fromDate(new Date(message.timestamp * 1000)),
        message_type: message.type,
        content: message.body || '',
        mentioned_ids: mentionedIds,
        mentions_andre: !!ownWid && mentionedIds.includes(ownWid),
        quoted_msg_id: rawQuotedId ? String(rawQuotedId) : null,
        quoted_from_me: typeof rawQuotedFromMe === 'boolean' ? rawQuotedFromMe : null,
        links: (message.links || []).map((l) => (typeof l === 'string' ? l : l.link)).filter(Boolean),
        transcription_text: null,
        transcription_model: null,
        ingested_at: admin.firestore.Timestamp.now(),
    };

    if (message.hasMedia) {
        const media = await captureMedia(message, chatId);
        if (media) {
            msgData.media = media;
        }
    }

    await db.collection('whatsapp_messages').doc(msgData.id).set(msgData, { merge: true });
    return msgData.id;
}

// ---------------------------------------------------------------------------
// Reparo de mídia: mensagens gravadas sem media.storage_path (falha de
// download/upload na captura ao vivo — DNS fora do ar, timeout do puppeteer)
// são retentadas enquanto a mensagem ainda existe no WhatsApp. Roda pós-ready
// e a cada hora; teto de tentativas por mensagem para não insistir em mídia
// que já não está mais disponível no aparelho.
const MEDIA_REPAIR_TYPES = new Set(['ptt', 'audio', 'image', 'video', 'document', 'sticker']);
const MEDIA_REPAIR_LOOKBACK_MS = 48 * 60 * 60 * 1000;
const MEDIA_REPAIR_MAX_ATTEMPTS = 3;
const MEDIA_REPAIR_READY_DELAY_MS = 2 * 60 * 1000;
let isRepairingMedia = false;

async function repairMissingMedia() {
    if (!isClientReady || isRepairingMedia) {
        return;
    }
    isRepairingMedia = true;
    try {
        const cutoff = admin.firestore.Timestamp.fromMillis(Date.now() - MEDIA_REPAIR_LOOKBACK_MS);
        const snap = await db.collection('whatsapp_messages').where('timestamp', '>=', cutoff).get();
        const broken = snap.docs.filter((docSnap) => {
            const m = docSnap.data();
            return MEDIA_REPAIR_TYPES.has(String(m.message_type))
                && !(m.media && m.media.storage_path)
                // Mensagens importadas de exports .txt não têm mídia real no WhatsApp.
                && !String(docSnap.id).includes('_txt_')
                && (m.media_repair_attempts || 0) < MEDIA_REPAIR_MAX_ATTEMPTS
                && !!m.wa_message_id;
        });
        if (!broken.length) {
            return;
        }
        console.log(`[MediaRepair] ${broken.length} mensagem(ns) com mídia pendente; tentando recuperar...`);
        const exhausted = [];
        for (const docSnap of broken) {
            const data = docSnap.data();
            const serializedId = data.wa_serialized_id
                || `${data.from_me ? 'true' : 'false'}_${data.chat_id}_${data.wa_message_id}`;
            try {
                const message = await client.getMessageById(serializedId);
                if (!message) {
                    throw new Error('mensagem não encontrada no WhatsApp');
                }
                const media = await captureMedia(message, data.chat_id);
                if (!media || !media.storage_path) {
                    throw new Error('download/upload não concluído');
                }
                await docSnap.ref.set({ media }, { merge: true });
                console.log(`[MediaRepair] Mídia recuperada: ${docSnap.id} -> ${media.storage_path}`);
            } catch (e) {
                const attempts = (data.media_repair_attempts || 0) + 1;
                await docSnap.ref.set({ media_repair_attempts: attempts }, { merge: true }).catch(() => {});
                console.error(`[MediaRepair] Falha em ${docSnap.id} (tentativa ${attempts}/${MEDIA_REPAIR_MAX_ATTEMPTS}):`, e.message || e);
                if (attempts >= MEDIA_REPAIR_MAX_ATTEMPTS) {
                    exhausted.push(`${data.chat_name || data.chat_id} (${data.message_type})`);
                }
            }
        }
        if (exhausted.length) {
            await sendTelegramAlert(
                `⚠️ Hermes WhatsApp: não consegui recuperar a mídia de ${exhausted.length} mensagem(ns) mesmo após ${MEDIA_REPAIR_MAX_ATTEMPTS} tentativas: ` +
                `${exhausted.slice(0, 5).join(', ')}${exhausted.length > 5 ? '…' : ''}. O conteúdo pode não estar mais disponível.`
            );
        }
    } catch (e) {
        console.error('[MediaRepair] Falha na varredura:', e);
    } finally {
        isRepairingMedia = false;
    }
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

        if (!deveCapturar(chatId)) {
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

// --- Recuperação retroativa no boot ---
// A captura ao vivo (message_create) perde tudo que chega com o worker desligado.
// Ao ficar pronto, varremos os chats da allowlist e completamos o que faltou via o
// mesmo backfillChatHistory do sync sob demanda (dedup pelo id determinístico
// chatId_msgId, então rodar de novo é inofensivo). A profundidade da busca usa o
// unreadCount do chat como pista — mensagens já lidas no celular também entram,
// pela janela mínima de RECOVERY_BASE_LIMIT. Chats sem atividade nova (último
// timestamp do chat <= último gravado no Firestore) são pulados sem fetch.
// A triagem e a Caixa de Entrada leem por ingested_at, então o que entrar aqui
// segue o fluxo normal de vinculação como se tivesse acabado de chegar.
const RECOVERY_READY_DELAY_MS = 90_000; // depois do syncChatRegistry (60s), com folga p/ hidratar
const RECOVERY_BASE_LIMIT = 50;
const RECOVERY_CHAT_PAUSE_MS = 1_500;
let isRecoveringMissed = false;

async function getLastStoredTimestampMs(chatId) {
    const snap = await db.collection('whatsapp_messages')
        .where('chat_id', '==', chatId)
        .orderBy('timestamp', 'desc')
        .limit(1)
        .get();
    if (snap.empty) return 0;
    const ts = snap.docs[0].get('timestamp');
    return ts && typeof ts.toMillis === 'function' ? ts.toMillis() : 0;
}

/**
 * Quais chats a recuperação do boot deve varrer.
 *
 * Com allowlist, são os chats da lista — poucos, e todos interessam.
 *
 * Com `capturar_todos`, varrer os ~700 chats conhecidos custaria mais de meia
 * hora só de pausa entre eles, e a esmagadora maioria não tem nada de novo:
 * na medição de 27/08/2026, 130 de 697 tiveram atividade em duas semanas. Então
 * o alvo passa a ser quem o WhatsApp diz ter mexido recentemente, ou tem não
 * lida — que é onde as mensagens perdidas de fato estão.
 */
async function alvosDaRecuperacao() {
    if (!capturarTodos) return [...chatsAllowlist];

    const corteMs = Date.now() - RECOVERY_JANELA_DIAS * 24 * 60 * 60 * 1000;
    try {
        const todos = await client.getChats();
        const alvos = [];
        for (const chat of Array.isArray(todos) ? todos : []) {
            const chatId = chat?.id?._serialized || (typeof chat?.id === 'string' ? chat.id : null);
            if (!chatId) continue;
            const ultimaMs = Number(chat?.lastMessage?.timestamp || chat?.timestamp || 0) * 1000;
            const naoLidas = Number(chat?.unreadCount) || 0;
            if (naoLidas > 0 || (ultimaMs && ultimaMs >= corteMs)) alvos.push(chatId);
        }
        // A allowlist entra sempre: são as conversas que o agente lê, e um buraco
        // ali é mais caro do que num chat qualquer.
        for (const chatId of chatsAllowlist) {
            if (!alvos.includes(chatId)) alvos.push(chatId);
        }
        if (alvos.length > RECOVERY_MAX_CHATS) {
            console.warn(`[Recovery] ${alvos.length} chats elegíveis; varrendo os `
                + `primeiros ${RECOVERY_MAX_CHATS}. O restante entra na próxima passagem.`);
            return alvos.slice(0, RECOVERY_MAX_CHATS);
        }
        return alvos;
    } catch (e) {
        console.error('[Recovery] Falha ao listar chats; caindo na allowlist:', e.message || e);
        return [...chatsAllowlist];
    }
}

async function recoverMissedMessages() {
    if (!isClientReady || isRecoveringMissed) return;
    if (!allowlistLoaded) {
        // Config ainda não chegou do Firestore — tenta de novo em 60s.
        console.log('[Recovery] Allowlist ainda não carregada — nova tentativa em 60s.');
        setTimeout(recoverMissedMessages, 60_000);
        return;
    }
    const alvos = await alvosDaRecuperacao();
    if (alvos.length === 0) {
        console.log('[Recovery] Nenhum chat a recuperar.');
        return;
    }

    isRecoveringMissed = true;
    const startedAt = Date.now();
    let chatsChecked = 0;
    let chatsBackfilled = 0;
    let totalStored = 0;
    try {
        console.log(`[Recovery] Verificando ${alvos.length} chat(s) por mensagens perdidas...`);
        for (const chatId of alvos) {
            if (!isClientReady) break; // desconectou no meio; o próximo ready recomeça
            try {
                const chat = await client.getChatById(chatId);
                chatsChecked++;
                const lastChatMs = Number(chat?.lastMessage?.timestamp || chat?.timestamp || 0) * 1000;
                const lastStoredMs = await getLastStoredTimestampMs(chatId);
                if (lastChatMs && lastStoredMs && lastChatMs <= lastStoredMs) continue; // nada perdido
                const unread = Number(chat?.unreadCount) || 0;
                const limitCount = Math.min(Math.max(RECOVERY_BASE_LIMIT, unread + 10), MAX_SYNC_LIMIT);
                let { fetched, stored } = await backfillChatHistory(chatId, limitCount);
                // Janela saturada (tudo que veio era novo): o buraco pode ser mais fundo
                // que a janela — refaz uma vez com o teto. Dedup torna a repetição barata.
                if (stored === fetched && fetched >= limitCount && limitCount < MAX_SYNC_LIMIT) {
                    const retry = await backfillChatHistory(chatId, MAX_SYNC_LIMIT);
                    fetched = retry.fetched;
                    stored += retry.stored;
                }
                if (stored > 0) {
                    chatsBackfilled++;
                    totalStored += stored;
                    console.log(`[Recovery] Chat ${chatId}: ${stored} mensagem(ns) recuperada(s) de ${fetched} verificada(s).`);
                }
            } catch (chatErr) {
                console.error(`[Recovery] Falha no chat ${chatId}:`, chatErr.message || chatErr);
            }
            // Pausa curta entre chats para não martelar o WhatsApp Web logo no boot.
            await new Promise((resolve) => setTimeout(resolve, RECOVERY_CHAT_PAUSE_MS));
        }
        console.log(`[Recovery] Concluída em ${Math.round((Date.now() - startedAt) / 1000)}s: ${totalStored} mensagem(ns) recuperada(s) em ${chatsBackfilled} de ${chatsChecked} chat(s) verificado(s).`);
        await db.collection('system').doc('whatsapp_worker').set({
            last_recovery_at: admin.firestore.Timestamp.now(),
            last_recovery_stored: totalStored,
            last_recovery_chats_backfilled: chatsBackfilled,
        }, { merge: true });
    } catch (e) {
        console.error('[Recovery] Falha na recuperação retroativa:', e.message || e);
    } finally {
        isRecoveringMissed = false;
    }
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
        // Mesmo critério da captura ao vivo — não busca histórico de chat que não é capturado.
        if (!deveCapturar(chatId)) {
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

// Varredura horária de reparo de mídia (além da passada pós-ready) — recupera
// mídias cujo download/upload falhou na captura ao vivo.
cron.schedule('7 * * * *', () => {
    repairMissingMedia().catch((e) => console.error('[MediaRepair] Falha na varredura horária:', e));
});

cron.schedule('*/5 * * * *', async () => {
    await writeHeartbeat();
    if (isClientReady && (Date.now() - lastChatsSyncMs >= CHATS_SYNC_INTERVAL_MS)) {
        syncChatRegistry().catch((e) => console.error('[Chats] Falha no cron de sincronização de chats:', e));
    }
});

/**
 * Para onde a mensagem vai de fato.
 *
 * A versao anterior colava `@c.us` no que viesse: `+5527998754054` virava
 * `+5527998754054@c.us`, e JID do WhatsApp nao leva `+`. Foi o que derrubou os
 * dois envios de 28/08/2026 — aceitos na fila, recusados no envio, com a
 * excecao minificada `t: t` como unica explicacao.
 *
 * `client.getNumberId` e a resolucao da propria biblioteca: consulta se o
 * numero existe no WhatsApp e devolve o WID correto. Resolve de uma vez o `+`,
 * variacoes de formatacao e o nono digito — e, quando o numero nao esta no
 * WhatsApp, diz isso em vez de falhar sem motivo legivel.
 */
async function resolverDestino(toNumber) {
    const bruto = String(toNumber || '').trim();
    if (/@(c\.us|g\.us|lid|broadcast)$/.test(bruto)) return bruto;

    const digitos = bruto.replace(/[^0-9]/g, '');
    if (digitos.length < 8) {
        throw new Error(`numero de destino invalido: "${toNumber}"`);
    }

    const wid = await client.getNumberId(digitos);
    if (!wid) {
        throw new Error(
            `o numero ${digitos} nao esta no WhatsApp (ou nao pode ser verificado agora)`);
    }
    return wid._serialized;
}

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
                const destino = await resolverDestino(toNumber);
                const enviada = await client.sendMessage(destino, content);

                await doc.ref.update({
                    status: 'sent',
                    sent_at: admin.firestore.Timestamp.now(),
                    // Guarda para onde foi de verdade e o id da mensagem: sem isso,
                    // "enviada" e uma afirmacao sem prova.
                    sent_to: destino,
                    wa_message_id: enviada?.id?.id || null,
                    error_message: admin.firestore.FieldValue.delete(),
                    updated_at: admin.firestore.Timestamp.now()
                });
                console.log(`Message sent to ${toNumber} (${destino})`);

            } catch (error) {
                // A excecao do WhatsApp Web vem minificada — o erro real das duas
                // tentativas de 28/08 era literalmente `t: t`, inutil para quem le.
                // Guardar tambem o nome e a pilha da origem torna a proxima
                // investigacao possivel sem precisar do log do processo.
                const detalhe = error?.message || String(error);
                console.error(`Failed to send message to ${toNumber}:`, error);
                await doc.ref.update({
                    status: 'failed',
                    error_message: detalhe.length > 2 ? detalhe
                        : `WhatsApp Web recusou o envio (erro minificado "${detalhe}") — `
                          + 'geralmente destino invalido ou numero fora do WhatsApp.',
                    error_origem: String(error?.stack || '').split(/\r?\n/)[1]?.trim() || null,
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

// --- Desligamento limpo ---
//
// Até 27/08/2026 não havia nenhum: parar o worker matava o processo com o
// Chromium do puppeteer ainda segurando o perfil do LocalAuth. É de onde vem o
// EBUSY que já obrigou a reautenticar por QR — e reautenticar exige o celular
// do dono, então uma parada suja custa muito mais do que parece.
//
// `client.destroy()` fecha o browser e solta o lock. O timeout existe porque
// travar no desligamento seria o mesmo problema com outro nome: passados
// alguns segundos, sai de qualquer jeito.
let desligando = false;
async function desligar(sinal) {
    if (desligando) return;
    desligando = true;
    console.log(`[Shutdown] ${sinal} recebido — fechando o cliente do WhatsApp...`);
    const prazo = setTimeout(() => {
        console.warn('[Shutdown] Tempo esgotado ao fechar; saindo assim mesmo.');
        process.exit(1);
    }, 15_000);
    try {
        await client.destroy();
        console.log('[Shutdown] Cliente fechado, sessão preservada.');
    } catch (e) {
        console.error('[Shutdown] Falha ao fechar o cliente:', e?.message || e);
    } finally {
        clearTimeout(prazo);
        process.exit(0);
    }
}
process.on('SIGINT', () => desligar('SIGINT'));
process.on('SIGTERM', () => desligar('SIGTERM'));
