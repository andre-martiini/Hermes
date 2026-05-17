import { Client, LocalAuth } from 'whatsapp-web.js';
import qrcode from 'qrcode-terminal';
import cron from 'node-cron';
import admin from 'firebase-admin';

// Initialize Firebase Admin (assuming default credentials in environment)
if (!admin.apps.length) {
    admin.initializeApp();
}

const db = admin.firestore();
const FieldValue = admin.firestore.FieldValue;

const client = new Client({
    authStrategy: new LocalAuth()
});

let isClientReady = false;
let isProcessingOutbox = false;

client.on('qr', (qr) => {
    qrcode.generate(qr, { small: true });
    console.log('Scan the QR code above to authenticate.');
});

client.on('ready', () => {
    console.log('WhatsApp client is ready!');
    isClientReady = true;
});

client.on('auth_failure', (msg) => {
    console.error('Authentication failure:', msg);
});

client.on('disconnected', (reason) => {
    console.log('Client was disconnected', reason);
    isClientReady = false;
});

// PASSIVE MODULE: Listen to incoming messages
client.on('message', async (message) => {
    try {
        console.log(`Received message from ${message.from}`);
        const contact = await message.getContact();

        const msgData = {
            id: admin.firestore.Timestamp.now().toMillis().toString() + '_' + message.id.id,
            wa_message_id: message.id.id,
            contact_name: contact.name || contact.pushname || 'Unknown',
            contact_name_normalized: (contact.name || contact.pushname || 'Unknown').toLowerCase(),
            timestamp: admin.firestore.Timestamp.fromDate(new Date(message.timestamp * 1000)),
            message_type: message.type,
            content: message.body || '',
            links: message.links || [],
            transcription_text: null,
            transcription_model: null,
        };

        if (message.hasMedia) {
            const media = await message.downloadMedia();
            if (media) {
                // To fully match the documentation, we'd upload to Storage here.
                // For simplicity in this standalone worker, we store the metadata.
                msgData.media = {
                    mimeType: media.mimetype,
                    sizeBytes: media.data.length * (3/4) // approx base64 size
                };

                // Audio messages could be transcribed by Whisper here (transcription model).
                // Example structure if it was transcribed:
                // msgData.transcription_text = 'Hello world';
                // msgData.transcription_model = 'whisper-1';
            }
        }

        await db.collection('whatsapp_messages').doc(msgData.id).set(msgData);
        console.log(`Stored message ${msgData.id} in whatsapp_messages.`);

    } catch (error) {
        console.error('Error handling incoming message:', error);
    }
});

client.initialize();

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

// ACTIVE MODULE: Outbox checking cron job
cron.schedule('* * * * *', async () => {
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
