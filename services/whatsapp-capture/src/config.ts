export interface WhatsAppCaptureConfig {
  firebaseStorageBucket?: string;
  firebaseServiceAccountJson?: string;
  groqApiKey: string;
  whatsappSessionPath: string;
  firestoreCollection: string;
}

const readRequired = (key: string): string => {
  const value = process.env[key];
  if (!value) {
    throw new Error(`Variável obrigatória ausente: ${key}`);
  }
  return value;
};

export const config: WhatsAppCaptureConfig = {
  firebaseStorageBucket: process.env.FIREBASE_STORAGE_BUCKET,
  firebaseServiceAccountJson: process.env.FIREBASE_SERVICE_ACCOUNT_JSON,
  groqApiKey: readRequired('GROQ_API_KEY'),
  whatsappSessionPath: process.env.WHATSAPP_SESSION_PATH ?? '.wwebjs_auth',
  firestoreCollection: process.env.WHATSAPP_MESSAGES_COLLECTION ?? 'whatsapp_messages',
};
