import 'dotenv/config';
import qrcode from 'qrcode-terminal';
import WhatsAppWeb from 'whatsapp-web.js';
import { config } from './config.js';
import { processIncomingMessage } from './messageProcessor.js';

const { Client, LocalAuth } = WhatsAppWeb;

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: config.whatsappSessionPath }),
  puppeteer: {
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  },
});

client.on('qr', (qr: string) => {
  console.log('\nEscaneie o QR Code abaixo com o WhatsApp:');
  qrcode.generate(qr, { small: true });
});

client.on('authenticated', () => {
  console.log('WhatsApp autenticado com sucesso.');
});

client.on('ready', () => {
  console.log('Cliente WhatsApp pronto e ouvindo mensagens recebidas.');
});

client.on('auth_failure', (reason: string) => {
  console.error('Falha de autenticação no WhatsApp:', reason);
});

client.on('disconnected', (reason: string) => {
  console.error('Cliente desconectado:', reason);
});

client.on('message', async (message) => {
  if (message.fromMe) {
    return;
  }

  try {
    await processIncomingMessage(message);
    console.log(`[OK] ${message.type} | ${message.from}`);
  } catch (error) {
    console.error('[ERRO] Falha ao processar mensagem:', error);
  }
});

const start = async (): Promise<void> => {
  console.log('Iniciando microsserviço de captura WhatsApp...');
  await client.initialize();
};

start().catch((error) => {
  console.error('Erro fatal ao iniciar serviço:', error);
  process.exit(1);
});
