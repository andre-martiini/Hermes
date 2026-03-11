import admin from 'firebase-admin';
import { config } from './config.js';
import type { StoredMedia, WhatsAppMessageRecord } from './types.js';

const bootstrapFirebase = () => {
  if (admin.apps.length > 0) {
    return;
  }

  if (config.firebaseServiceAccountJson) {
    const serviceAccount = JSON.parse(config.firebaseServiceAccountJson);
    admin.initializeApp({
      credential: admin.credential.cert(serviceAccount),
      storageBucket: config.firebaseStorageBucket,
    });
    return;
  }

  admin.initializeApp({
    credential: admin.credential.applicationDefault(),
    storageBucket: config.firebaseStorageBucket,
  });
};

bootstrapFirebase();

const db = admin.firestore();
const bucket = admin.storage().bucket();

export const saveMessageRecord = async (record: WhatsAppMessageRecord): Promise<void> => {
  await db.collection(config.firestoreCollection).doc(record.id).set(record, { merge: true });
};

export const uploadMediaToStorage = async (
  messageId: string,
  fileName: string,
  mimeType: string,
  payload: Buffer,
): Promise<StoredMedia> => {
  const safeFileName = fileName.replace(/[^a-zA-Z0-9._-]/g, '_');
  const storagePath = `whatsapp_media/${messageId}/${Date.now()}_${safeFileName}`;
  const file = bucket.file(storagePath);

  await file.save(payload, {
    contentType: mimeType,
    resumable: false,
    metadata: {
      cacheControl: 'public,max-age=31536000',
    },
  });

  const [url] = await file.getSignedUrl({
    action: 'read',
    expires: '2500-01-01',
  });

  return {
    path: storagePath,
    url,
    mimeType,
    fileName: safeFileName,
    sizeBytes: payload.length,
  };
};
