const functions = require('firebase-functions');
const admin = require('firebase-admin');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const iconv = require('iconv-lite');
const axios = require('axios');
const { google } = require('googleapis');
const { PubSub } = require('@google-cloud/pubsub');
const { v4: uuidv4 } = require('uuid');

puppeteer.use(StealthPlugin());
if (admin.apps.length === 0) admin.initializeApp();

const db = admin.firestore();
const pubsub = new PubSub();

async function getGoogleAuth() {
    const credsDoc = await db.collection('system').document('google_credentials').get();
    if (!credsDoc.exists) {
        throw new Error("Credenciais do Google não encontradas no Firestore.");
    }
    const credsData = credsDoc.data();
    const oauth2Client = new google.auth.OAuth2(
        credsData.client_id,
        credsData.client_secret,
        credsData.token_uri
    );
    oauth2Client.setCredentials({
        access_token: credsData.token,
        refresh_token: credsData.refresh_token
    });
    return oauth2Client;
}

async function uploadToDrive(fileName, content, mimeType, folderId) {
    const auth = await getGoogleAuth();
    const drive = google.drive({ version: 'v3', auth });

    const fileMetadata = {
        name: fileName,
        parents: folderId ? [folderId] : []
    };

    const media = {
        mimeType: mimeType,
        body: require('stream').Readable.from(content)
    };

    const file = await drive.files.create({
        resource: fileMetadata,
        media: media,
        fields: 'id, webViewLink'
    });

    return file.data;
}

async function runScraper(data) {
    const { taskId, processoSei, folderId } = data;
    console.log(`Iniciando scraper para tarefa ${taskId}, processo ${processoSei}`);

    const match = processoSei.match(/(\d+)\.(\d+)\/(\d+)-(\d+)/);
    if (!match) throw new Error("Formato do processo inválido.");

    const [_, radical, numero, ano, dv] = match;

    const browser = await puppeteer.launch({
        headless: "new",
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    try {
        const page = await browser.newPage();
        await page.goto('https://sipac.ifes.edu.br/public/jsp/portal.jsf', { waitUntil: 'networkidle2' });

        await page.waitForSelector('input[id$="n_proc_p"]', { timeout: 15000 });

        await page.type('input[id$="n_proc_p"]', radical);
        await page.type('input[id$="n_proc_p2"]', numero).catch(() => {});
        await page.type('input[id$="n_proc_p3"]', ano).catch(() => {});
        await page.type('input[id$="n_proc_p4"]', dv).catch(() => {});

        if (!(await page.$('input[id$="n_proc_p2"]'))) {
             await page.type('input[id$="num_proc"]', numero).catch(() => {});
             await page.type('input[id$="ano_proc"]', ano).catch(() => {});
             await page.type('input[id$="dv_proc"]', dv).catch(() => {});
        }

        await Promise.all([
            page.click('input[value="Consultar Processo"], input[id*="consultar"]'),
            page.waitForNavigation({ waitUntil: 'networkidle2' })
        ]);

        const processLink = await page.$('a[id*="visualizar"], a[title*="Visualizar"]');
        if (processLink) {
            await Promise.all([
                processLink.click(),
                page.waitForNavigation({ waitUntil: 'networkidle2' })
            ]);
        }

        const metadata = await page.evaluate(() => {
            const data = {};
            const labels = Array.from(document.querySelectorAll('label, th, td.label'));
            labels.forEach(label => {
                const text = label.innerText.trim();
                if (text.includes('Interessado:')) data.interessado = label.nextElementSibling?.innerText.trim();
                if (text.includes('Assunto:')) data.assunto = label.nextElementSibling?.innerText.trim();
            });
            return data;
        });

        const docs = await page.evaluate(() => {
            const items = [];
            const rows = Array.from(document.querySelectorAll('tr'));
            rows.forEach((row, idx) => {
                const links = Array.from(row.querySelectorAll('a'));
                const docLink = links.find(a => a.href.includes('download') || a.onclick?.toString().includes('visualizarDocumento'));
                if (docLink) {
                    items.push({
                        nome: row.innerText.split('\n')[0].trim() || `Documento ${idx}`,
                        url: docLink.href,
                        isJSF: !!docLink.onclick
                    });
                }
            });
            return items;
        });

        const poolItems = [];

        for (const docItem of docs) {
            try {
                let content;
                let mimeType = 'application/pdf';
                let fileName = docItem.nome.replace(/[/\\?%*:|"<>]/g, '-') + '.pdf';

                if (docItem.nome.toLowerCase().includes('despacho') || docItem.nome.toLowerCase().includes('html')) {
                    mimeType = 'text/html';
                    fileName = docItem.nome.replace(/[/\\?%*:|"<>]/g, '-') + '.html';
                }

                if (docItem.isJSF) {
                    const newPagePromise = new Promise(x => browser.once('targetcreated', target => x(target.page())));
                    await page.evaluate((url) => {
                        const links = Array.from(document.querySelectorAll('a'));
                        const link = links.find(a => a.href === url || a.onclick?.toString().includes(url));
                        if (link) link.click();
                    }, docItem.url);

                    const docPage = await newPagePromise;
                    if (docPage) {
                        await docPage.waitForNetworkIdle();
                        if (mimeType === 'text/html') {
                            const html = await docPage.content();
                            content = Buffer.from(html, 'utf8');
                        } else {
                            const url = docPage.url();
                            const cookies = await docPage.cookies();
                            const cookieStr = cookies.map(c => `${c.name}=${c.value}`).join('; ');
                            const resp = await axios.get(url, { responseType: 'arraybuffer', headers: { 'Cookie': cookieStr } });
                            content = Buffer.from(resp.data);
                        }
                        await docPage.close();
                    }
                } else {
                    const resp = await axios.get(docItem.url, { responseType: 'arraybuffer' });
                    content = Buffer.from(resp.data);
                    if (mimeType === 'text/html') {
                        const decoded = iconv.decode(content, 'ISO-8859-1');
                        content = Buffer.from(decoded, 'utf8');
                    }
                }

                if (content) {
                    const driveFile = await uploadToDrive(fileName, content, mimeType, folderId);
                    poolItems.push({
                        id: uuidv4().substring(0, 9),
                        tipo: 'arquivo',
                        valor: driveFile.webViewLink,
                        nome: docItem.nome,
                        data_criacao: new Date().toISOString(),
                        drive_file_id: driveFile.id
                    });
                }
            } catch (err) {
                console.error(`Erro ao processar ${docItem.nome}:`, err);
            }
        }

        await db.collection('tarefas').doc(taskId).update({
            sync_status: 'concluido',
            pool_dados: admin.firestore.FieldValue.arrayUnion(...poolItems)
        });

        // Notifica vetorização via PubSub
        const topicName = 'vectorize-process';
        const dataBuffer = Buffer.from(JSON.stringify({ taskId }));
        await pubsub.topic(topicName).publish(dataBuffer);

        return { count: poolItems.length };

    } finally {
        await browser.close();
    }
}

exports.scrapeSipacPubSub = functions.runWith({
    timeoutSeconds: 540,
    memory: '2GB'
}).pubsub.topic('scrape-sipac').onPublish(async (message) => {
    const data = message.json;
    try {
        await runScraper(data);
    } catch (error) {
        console.error("Erro no scrapeSipacPubSub:", error);
        if (data.taskId) {
            await db.collection('tarefas').doc(data.taskId).update({ sync_status: 'erro' });
        }
    }
});

exports.scrapeSipac = functions.runWith({
    timeoutSeconds: 540,
    memory: '2GB'
}).https.onCall(async (data, context) => {
    // Apenas dispara o PubSub e retorna rápido para o frontend
    const topicName = 'scrape-sipac';
    const dataBuffer = Buffer.from(JSON.stringify(data));
    await pubsub.topic(topicName).publish(dataBuffer);

    if (data.taskId) {
        await db.collection('tarefas').doc(data.taskId).update({ sync_status: 'processando' });
    }
    return { success: true, message: "Sincronização iniciada em segundo plano." };
});
