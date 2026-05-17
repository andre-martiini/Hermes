import { Client, LocalAuth } from 'whatsapp-web.js';
import qrcode from 'qrcode-terminal';
import cron from 'node-cron';
import admin from 'firebase-admin';

// Initialize Firebase Admin (assuming default credentials in environment)
if (!admin.apps.length) {
    admin.initializeApp();
}

const db = admin.firestore();

const client = new Client({
    authStrategy: new LocalAuth()
});

let isClientReady = false;

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

// ACTIVE MODULE: Outbox checking cron job
cron.schedule('* * * * *', async () => {
    if (!isClientReady) {
        console.log('Skipping cron tick: WhatsApp client not ready.');
        return;
    }

    try {
        const now = admin.firestore.Timestamp.now();

        // Fetch pending messages whose scheduled time has passed or is now
        const snapshot = await db.collection('whatsapp_outbox')
            .where('status', '==', 'pending')
            .where('scheduled_for', '<=', now)
            .get();

        if (snapshot.empty) {
            return;
        }

        for (const doc of snapshot.docs) {
            const data = doc.data();
            const toNumber = data.to_number;
            const content = data.content;

            if (!toNumber || !content) {
                console.error(`Invalid message data for doc ${doc.id}`);
                await doc.ref.update({
                    status: 'failed',
                    error_message: 'Missing to_number or content'
                });
                continue;
            }

            try {
                // Ensure the number is formatted correctly (e.g. 5527999999999@c.us)
                const formattedNumber = toNumber.includes('@c.us') ? toNumber : `${toNumber}@c.us`;

                await client.sendMessage(formattedNumber, content);

                // Update status to sent
                await doc.ref.update({
                    status: 'sent',
                    sent_at: admin.firestore.Timestamp.now()
                });
                console.log(`Message sent to ${toNumber}`);

            } catch (error) {
                // Log failure
                console.error(`Failed to send message to ${toNumber}:`, error);
                await doc.ref.update({
                    status: 'failed',
                    error_message: error.message || 'Unknown error'
                });
            }
        }
    } catch (err) {
        console.error('Error during outbox processing cron tick:', err);
    }
});
