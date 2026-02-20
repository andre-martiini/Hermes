const functions = require('firebase-functions/v1');
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
        // Aumenta o timeout para navegações pesadas do SIPAC
        page.setDefaultNavigationTimeout(60000);
        
        await page.goto('https://sipac.ifes.edu.br/public/jsp/portal.jsf', { waitUntil: 'networkidle2' });

        // Espera pelos campos de busca de processo
        await page.waitForSelector('input[name="RADICAL_PROTOCOLO"]', { timeout: 20000 });

        // Limpa e preenche os campos
        await page.$eval('input[name="RADICAL_PROTOCOLO"]', el => el.value = '');
        await page.type('input[name="RADICAL_PROTOCOLO"]', radical);
        
        await page.$eval('input[name="NUM_PROTOCOLO"]', el => el.value = '');
        await page.type('input[name="NUM_PROTOCOLO"]', numero);
        
        await page.$eval('input[name="ANO_PROTOCOLO"]', el => el.value = '');
        await page.type('input[name="ANO_PROTOCOLO"]', ano);
        
        await page.$eval('input[name="DV_PROTOCOLO"]', el => el.value = '');
        await page.type('input[name="DV_PROTOCOLO"]', dv);

        // Submete a consulta
        await Promise.all([
            page.click('input[value="Consultar Processo"]'),
            page.waitForNavigation({ waitUntil: 'networkidle2' })
        ]);

        // Verifica se caiu na lista de resultados ou direto no processo
        const processLink = await page.$('a[id*="visualizar"], a[title*="Visualizar"], img[src*="zoom.png"]');
        if (processLink) {
            await Promise.all([
                processLink.click(),
                page.waitForNavigation({ waitUntil: 'networkidle2' })
            ]);
        }

        // Extração de Metadados de Dados Gerais
        const metadata = await page.evaluate(() => {
            const data = {};
            const ths = Array.from(document.querySelectorAll('th'));
            ths.forEach(th => {
                const text = th.innerText.trim();
                // O HTML usa "Assunto do Processo:", "Assunto Detalhado:", etc.
                if (text.includes('Assunto do Processo:')) data.assunto = th.nextElementSibling?.innerText.trim();
                if (text.includes('Assunto Detalhado:')) data.assuntoDetalhado = th.nextElementSibling?.innerText.trim();
            });

            // Interessado: Pega da tabela de Interessados
            const tables = Array.from(document.querySelectorAll('table.subListagem'));
            const intTable = tables.find(t => t.innerText.includes('Interessados Deste Processo'));
            if (intTable) {
                const firstRow = intTable.querySelector('tbody tr');
                if (firstRow) {
                    const cells = firstRow.querySelectorAll('td');
                    if (cells.length >= 3) data.interessado = cells[2].innerText.trim();
                }
            }
            return data;
        });

        // Extração de Documentos
        const docs = await page.evaluate(() => {
            const items = [];
            const tables = Array.from(document.querySelectorAll('table.subListagem'));
            const docTable = tables.find(t => t.innerText.includes('Documentos do Processo'));
            
            if (docTable) {
                const rows = Array.from(docTable.querySelectorAll('tbody tr'));
                rows.forEach((row, idx) => {
                    const cells = Array.from(row.querySelectorAll('td'));
                    if (cells.length < 6) return; // Precisa de pelo menos 6 colunas

                    const nome = cells[1].innerText.trim();
                    // O link de download está na penúltima célula (índice 5)
                    const linkElement = cells[5].querySelector('a');
                    
                    if (linkElement) {
                        let url = '';
                        const onclick = linkElement.getAttribute('onclick');
                        
                        if (onclick && onclick.includes('window.open')) {
                            // Extrai o conteúdo entre aspas simples
                            const matches = onclick.match(/'([^']+)'/g);
                            if (matches && matches.length > 0) {
                                url = matches[0].replace(/'/g, '');
                            }
                        } else {
                            url = linkElement.href;
                        }

                        if (url && url !== '#' && !url.startsWith('javascript')) {
                            items.push({
                                nome: nome,
                                url: url.startsWith('http') ? url : window.location.origin + url,
                                isJSF: url.includes('.jsf') || (onclick && onclick.includes('.jsf'))
                            });
                        }
                    }
                });
            }
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
