const functions = require('firebase-functions/v1');
const admin = require('firebase-admin');
const { FieldValue } = require('firebase-admin/firestore');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const iconv = require('iconv-lite');
const axios = require('axios');
const { google } = require('googleapis');
const { PubSub } = require('@google-cloud/pubsub');
const { v4: uuidv4 } = require('uuid');
const Busboy = require('busboy');
const { scrapeSIPACProcess } = require('./sipacService');

puppeteer.use(StealthPlugin());
if (admin.apps.length === 0) admin.initializeApp();

const db = admin.firestore();
const pubsub = new PubSub();

async function getGoogleAuth() {
    const credsDoc = await db.collection('system').doc('google_credentials').get();
    if (!credsDoc.exists) {
        throw new Error("Credenciais do Google não encontradas no Firestore.");
    }
    const credsData = credsDoc.data();
    const oauth2Client = new google.auth.OAuth2(
        credsData.client_id,
        credsData.client_secret,
        credsData.token_uri
    );
    let expiryMillis = null;
    if (credsData.expiry_date) {
        if (typeof credsData.expiry_date.toMillis === 'function') {
            expiryMillis = credsData.expiry_date.toMillis();
        } else if (typeof credsData.expiry_date === 'number') {
            expiryMillis = credsData.expiry_date;
        } else if (typeof credsData.expiry_date === 'string') {
            expiryMillis = Date.parse(credsData.expiry_date);
        } else if (credsData.expiry_date._seconds !== undefined) {
            expiryMillis = credsData.expiry_date._seconds * 1000 + Math.floor((credsData.expiry_date._nanoseconds || 0) / 1000000);
        }
    } else if (credsData.expiry) {
        if (typeof credsData.expiry.toMillis === 'function') {
            expiryMillis = credsData.expiry.toMillis();
        } else if (typeof credsData.expiry === 'number') {
            expiryMillis = credsData.expiry;
        } else if (typeof credsData.expiry === 'string') {
            expiryMillis = Date.parse(credsData.expiry);
        } else if (credsData.expiry._seconds !== undefined) {
            expiryMillis = credsData.expiry._seconds * 1000 + Math.floor((credsData.expiry._nanoseconds || 0) / 1000000);
        }
    }

    oauth2Client.setCredentials({
        access_token: credsData.token,
        refresh_token: credsData.refresh_token,
        expiry_date: expiryMillis
    });

    const shouldRefresh = Boolean(
        credsData.refresh_token &&
        (!expiryMillis || Date.now() >= expiryMillis - 60_000)
    );

    if (shouldRefresh) {
        await oauth2Client.refreshAccessToken();
        const refreshed = oauth2Client.credentials || {};
        await db.collection('system').doc('google_credentials').update({
            token: refreshed.access_token || credsData.token,
            expiry_date: refreshed.expiry_date || null,
            updated_at: admin.firestore.FieldValue.serverTimestamp()
        });
    }

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
            pool_dados: FieldValue.arrayUnion(...poolItems)
        });

        // Mirror to Knowledge base
        for (const item of poolItems) {
            const knowledgeItem = {
                id: item.id,
                titulo: item.nome || 'Sem título',
                tipo_arquivo: item.nome?.split('.').pop()?.toLowerCase() || 'unknown',
                url_drive: item.valor,
                tamanho: 0,
                data_criacao: item.data_criacao,
                origem: { modulo: 'tarefas', id_origem: taskId },
                categoria: 'Ações'
            };
            await db.collection('conhecimento').doc(item.id).set(knowledgeItem);
        }

        // Notifica vetorização via PubSub
        const topicName = 'vectorize-process';
        const dataBuffer = Buffer.from(JSON.stringify({ taskId }));
        await pubsub.topic(topicName).publish(dataBuffer);

        return { count: poolItems.length };

    } finally {
        await browser.close();
    }
}

//exports.scrapeSipacPubSub = functions.runWith({
//    timeoutSeconds: 540,
//    memory: '2GB'
//}).pubsub.topic('scrape-sipac').onPublish(async (message) => {
//    const data = message.json;
//    try {
//        await runScraper(data);
//    } catch (error) {
//        console.error("Erro no scrapeSipacPubSub:", error);
//        if (data.taskId) {
//            await db.collection('tarefas').doc(data.taskId).update({ sync_status: 'erro' });
//        }
//    }
//    });

//exports.scrapeSipac = functions.runWith({
//    timeoutSeconds: 540,
//    memory: '2GB'
//}).https.onCall(async (data, context) => {
//    // Apenas dispara o PubSub e retorna rápido para o frontend
//    const topicName = 'scrape-sipac';
//    const dataBuffer = Buffer.from(JSON.stringify(data));
//    await pubsub.topic(topicName).publish(dataBuffer);

//    if (data.taskId) {
//        await db.collection('tarefas').doc(data.taskId).update({ sync_status: 'processando' });
//    }
//    return { success: true, message: "Sincronização iniciada em segundo plano." };
//});

// ─────────────────────────────────────────────────────────────────────────────
// uploadFileForCopiloto — Endpoint HTTP para ingestão documental do Copiloto
// Recebe multipart/form-data, autentica via Bearer token, faz upload para uma
// pasta isolada no Drive e retorna o driveFileId.
// ─────────────────────────────────────────────────────────────────────────────
exports.uploadFileForCopiloto = functions.runWith({
    timeoutSeconds: 300,
    memory: '1GB'
}).https.onRequest((req, res) => {
    // CORS
    res.set('Access-Control-Allow-Origin', '*');
    res.set('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.set('Access-Control-Allow-Headers', 'Authorization, Content-Type');

    if (req.method === 'OPTIONS') {
        return res.status(204).send('');
    }

    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Método não permitido.' });
    }

    // Verificação do token Firebase Auth
    const authHeader = req.headers['authorization'] || '';
    if (!authHeader.startsWith('Bearer ')) {
        return res.status(401).json({ error: 'Token de autenticação ausente.' });
    }

    const idToken = authHeader.slice(7);

    return admin.auth().verifyIdToken(idToken)
        .then(() => new Promise((resolve) => {
            const busboy = Busboy({ headers: req.headers, limits: { fileSize: 50 * 1024 * 1024 } }); // 50MB max
            let fileBuffer = null;
            let fileName = null;
            let mimeType = 'application/octet-stream';
            let fileTooLarge = false;

            busboy.on('file', (fieldname, file, info) => {
                fileName = info.filename || `upload_${Date.now()}`;
                mimeType = info.mimeType || 'application/octet-stream';
                const chunks = [];

                file.on('data', (chunk) => chunks.push(chunk));
                file.on('limit', () => { fileTooLarge = true; file.resume(); });
                file.on('end', () => {
                    if (!fileTooLarge) {
                        fileBuffer = Buffer.concat(chunks);
                    }
                });
            });

            busboy.on('finish', async () => {
                try {
                    if (fileTooLarge) {
                        res.status(413).json({ error: 'Arquivo excede o limite de 50MB.' });
                        return resolve();
                    }
                    if (!fileBuffer || !fileName) {
                        res.status(400).json({ error: 'Nenhum arquivo recebido no campo "file".' });
                        return resolve();
                    }

                    const auth = await getGoogleAuth();
                    const drive = google.drive({ version: 'v3', auth });

                    // Localiza ou cria a pasta isolada Hermes_Copiloto_Uploads
                    let folderId = null;
                    const folderSearch = await drive.files.list({
                        q: "name='Hermes_Copiloto_Uploads' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                        fields: 'files(id)',
                        spaces: 'drive'
                    });

                    if (folderSearch.data.files && folderSearch.data.files.length > 0) {
                        folderId = folderSearch.data.files[0].id;
                    } else {
                        const folderCreate = await drive.files.create({
                            requestBody: { name: 'Hermes_Copiloto_Uploads', mimeType: 'application/vnd.google-apps.folder' },
                            fields: 'id'
                        });
                        folderId = folderCreate.data.id;
                    }

                    const driveFile = await uploadToDrive(fileName, fileBuffer, mimeType, folderId);

                    res.status(200).json({
                        driveFileId: driveFile.id,
                        webViewLink: driveFile.webViewLink,
                        fileName,
                        mimeType
                    });
                    resolve();
                } catch (err) {
                    console.error('Erro em uploadFileForCopiloto:', err);
                    res.status(500).json({ error: err.message });
                    resolve();
                }
            });

            busboy.on('error', (err) => {
                console.error('Busboy error:', err);
                res.status(500).json({ error: err.message });
                resolve();
            });

            // Firebase Functions já consome o stream e expõe o body em req.rawBody.
            // Usar req.pipe() resulta em "Unexpected end of form" pois a stream está vazia.
            if (req.rawBody) {
                busboy.end(req.rawBody);
            } else {
                req.pipe(busboy);
            }
        }))
        .catch((authErr) => {
            console.error('Token inválido:', authErr);
            return res.status(401).json({ error: 'Token de autenticação inválido.' });
        });
});

exports.getQuotes = functions.runWith({
    timeoutSeconds: 60,
    memory: '2GB'
}).https.onCall(async (data, context) => {
    const { searchTerm } = data;
    if (!searchTerm) {
        throw new functions.https.HttpsError('invalid-argument', 'The function must be called with "searchTerm".');
    }

    const browser = await puppeteer.launch({
        headless: "new",
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    try {
        const page = await browser.newPage();
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36');

        // Search on Mercado Livre
        const searchUrl = `https://lista.mercadolivre.com.br/${encodeURIComponent(searchTerm)}`;
        await page.goto(searchUrl, { waitUntil: 'domcontentloaded' });

        // Wait for results
        await page.waitForSelector('.ui-search-layout__item', { timeout: 10000 });

        // Click the first result to get details
        const firstItem = await page.$('.ui-search-layout__item a');
        if (!firstItem) throw new Error('No results found');

        const itemUrl = await page.evaluate(el => el.href, firstItem);
        await page.goto(itemUrl, { waitUntil: 'networkidle2' });

        // Extract Data
        const price = await page.evaluate(() => {
            const priceElement = document.querySelector('.ui-pdp-price__second-line .andes-money-amount__fraction');
            return priceElement ? parseFloat(priceElement.innerText.replace(/\./g, '').replace(',', '.')) : 0;
        });

        const title = await page.evaluate(() => {
            const h1 = document.querySelector('h1.ui-pdp-title');
            return h1 ? h1.innerText : '';
        });

        const vendor = await page.evaluate(() => {
            const seller = document.querySelector('.ui-pdp-seller__link-trigger');
            return seller ? seller.innerText : 'Mercado Livre';
        });

        // Screenshot
        const screenshotBuffer = await page.screenshot({ fullPage: false });
        const fileName = `quotes/${Date.now()}_${searchTerm.replace(/[^a-z0-9]/gi, '_')}.png`;

        // Find folder ID from system/config or assume root (null)
        // Ideally we should fetch 'googleDriveFolderId' from Firestore if needed, but for now root is fine or existing logic
        let folderId = null;
        try {
             const configDoc = await db.collection('configuracoes').doc('geral').get();
             if (configDoc.exists) folderId = configDoc.data().googleDriveFolderId;
        } catch(e) {}

        const fileData = await uploadToDrive(fileName, screenshotBuffer, 'image/png', folderId);

        return {
            price,
            vendor,
            title,
            screenshotUrl: fileData.webViewLink,
            date: new Date().toISOString()
        };

    } catch (error) {
        console.error("Error in getQuotes:", error);
        throw new functions.https.HttpsError('internal', error.message);
    } finally {
        await browser.close();
    }
});


// ─────────────────────────────────────────────────────────────────────────────
// generatePdfFromHtml — Microserviço HTML to PDF (Deep Research MVP)
// Recebe HTML via POST e retorna Buffer PDF usando Puppeteer.
// Exige Bearer Token de segurança para prevenção contra abusos.
// ─────────────────────────────────────────────────────────────────────────────
exports.generatePdfFromHtml = functions.runWith({
    timeoutSeconds: 120,
    memory: '1GB'
}).https.onRequest(async (req, res) => {
    // CORS
    res.set('Access-Control-Allow-Origin', '*');
    res.set('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.set('Access-Control-Allow-Headers', 'Authorization, Content-Type');

    if (req.method === 'OPTIONS') {
        return res.status(204).send('');
    }

    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Método não permitido. Utilize POST.' });
    }

    if (!process.env.PUPPETEER_INTERNAL_SECRET) {
        console.error('PUPPETEER_INTERNAL_SECRET não configurado.');
        return res.status(503).json({ error: 'Serviço de PDF não configurado.' });
    }

    // Trava de segurança atômica via Header
    const authHeader = req.headers['authorization'] || '';
    if (!authHeader.startsWith('Bearer ') || authHeader.split(' ')[1] !== process.env.PUPPETEER_INTERNAL_SECRET) {
        return res.status(401).json({ error: 'Não autorizado. Token de serviço inválido.' });
    }

    const { html, pageFormat = 'A4' } = req.body || {};

    if (!html) {
        return res.status(400).json({ error: 'O payload HTML é obrigatório.' });
    }

    let browser;
    try {
        browser = await puppeteer.launch({
            headless: "new",
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });

        const page = await browser.newPage();
        await page.setContent(html, { waitUntil: 'networkidle0' });

        const pdfBuffer = await page.pdf({
            format: pageFormat,
            printBackground: true,
            margin: { top: '20px', bottom: '20px', left: '20px', right: '20px' }
        });

        res.setHeader('Content-Type', 'application/pdf');
        res.setHeader('Content-Disposition', 'attachment; filename=document.pdf');
        res.status(200).send(pdfBuffer);
    } catch (err) {
        console.error('Erro em generatePdfFromHtml:', err);
        res.status(500).json({ error: 'Erro interno ao gerar PDF.', details: err.message });
    } finally {
        if (browser) await browser.close();
    }
});

exports.consultarProcessoSipac = functions.runWith({
    timeoutSeconds: 300,
    memory: '2GB'
}).https.onCall(async (data, context) => {
    const userUid = context.auth ? context.auth.uid : (context.rawRequest && context.rawRequest.headers['x-hermes-user-uid']);
    if (!userUid) {
        throw new functions.https.HttpsError('unauthenticated', 'O usuário precisa estar autenticado.');
    }

    const { numeroProcesso } = data;
    if (!numeroProcesso) {
        throw new functions.https.HttpsError('invalid-argument', 'O número do processo é obrigatório.');
    }

    try {
        console.log(`[consultarProcessoSipac] Iniciando busca para o processo: ${numeroProcesso}`);
        const result = await scrapeSIPACProcess(numeroProcesso);
        return result;
    } catch (error) {
        console.error('[consultarProcessoSipac Error]', error);
        throw new functions.https.HttpsError('internal', error.message || 'Erro ao consultar o processo no SIPAC.');
    }
});

function buildSipacChangeSummary(oldData, newResult) {
    const changes = [];

    const oldStatus = (oldData.status || '').trim();
    const newStatus = (newResult.status || '').trim();
    if (oldStatus && newStatus && oldStatus !== newStatus) {
        changes.push(`📋 Status: ${oldStatus} → ${newStatus}`);
    }

    const oldUnit = (oldData.unidadeAtual || '').trim();
    const newUnit = (newResult.unidadeAtual || '').trim();
    if (oldUnit && newUnit && oldUnit !== newUnit) {
        changes.push(`📍 Movimentado: ${oldUnit} → ${newUnit}`);
    }

    const oldDocCount = Array.isArray(oldData.documentos)
        ? oldData.documentos.length
        : parseInt(oldData.totalDocumentos || '0', 10);
    const newDocCount = Array.isArray(newResult.documentos) ? newResult.documentos.length : 0;
    if (newDocCount > oldDocCount) {
        const diff = newDocCount - oldDocCount;
        const newDocs = newResult.documentos.slice(-diff);
        const docDetails = newDocs.map(d => `${d.tipo || 'Documento'} (${d.data || ''})`).join(', ');
        changes.push(`📄 ${diff} novo(s) documento(s): ${docDetails}`);
    }

    const oldMovCount = Array.isArray(oldData.movimentacoes) ? oldData.movimentacoes.length : 0;
    const newMovCount = Array.isArray(newResult.movimentacoes) ? newResult.movimentacoes.length : 0;
    if (newMovCount > oldMovCount) {
        const diff = newMovCount - oldMovCount;
        const newMovs = newResult.movimentacoes.slice(-diff);
        const movDetails = newMovs
            .map(m => `${m.unidadeOrigem || ''} → ${m.unidadeDestino || ''} (${m.data || ''})`)
            .join('; ');
        changes.push(`🔄 ${diff} nova(s) movimentação(ões): ${movDetails}`);
    }

    return changes.length > 0 ? changes.join('\n') : null;
}

exports.scheduledSipacSync = functions.runWith({
    timeoutSeconds: 540,
    memory: '2GB'
}).pubsub.schedule('every 2 hours').onRun(async (context) => {
    console.log('[scheduledSipacSync] Starting background sync for SIPAC tracked processes...');
    const snapshot = await db.collection('sipac_processos').where('acompanhar', '==', true).get();
    if (snapshot.empty) {
        console.log('[scheduledSipacSync] No tracked processes found.');
        return null;
    }

    console.log(`[scheduledSipacSync] Found ${snapshot.size} processes to sync.`);
    const { scrapeSIPACProcess } = require('./sipacService');

    for (const doc of snapshot.docs) {
        const data = doc.data();
        const numeroProcesso = data.numeroProcesso;
        const oldHash = data.snapshot_hash || '';
        const uid = data.uid;

        console.log(`[scheduledSipacSync] Syncing process ${numeroProcesso} for user ${uid}...`);
        try {
            const result = await scrapeSIPACProcess(numeroProcesso);

            if (result.scraping_last_error) {
                console.warn(`[scheduledSipacSync] Failed to scrape ${numeroProcesso}: ${result.scraping_last_error}`);
                continue;
            }

            const newHash = result.snapshot_hash;
            if (newHash !== oldHash) {
                console.log(`[scheduledSipacSync] Change detected for process ${numeroProcesso}! Old hash: ${oldHash}, New hash: ${newHash}`);

                await doc.ref.update({
                    ...result,
                    ultimaConsulta: new Date().toISOString()
                });

                const notificationId = `sipac_${numeroProcesso.replace(/[^\d]/g, '')}_${Date.now()}`;
                const changeSummary = buildSipacChangeSummary(data, result);
                const baseMessage = `O processo foi atualizado.\nStatus atual: ${result.status}\nLocalização: ${result.unidadeAtual}`;
                const notificationMessage = changeSummary
                    ? `${baseMessage}\n\nO que mudou:\n${changeSummary}`
                    : baseMessage;
                const assuntoLabel = result.assuntoDetalhado
                    || (result.assuntoCodigo && result.assuntoDescricao
                        ? `${result.assuntoCodigo} - ${result.assuntoDescricao}`
                        : (result.assuntoDescricao || result.assuntoCodigo || ''));
                const notificationDoc = {
                    id: notificationId,
                    title: `Alteração no SIPAC: ${numeroProcesso}`,
                    message: notificationMessage,
                    assunto: assuntoLabel,
                    // Campo explícito para on_notificacao_created (main.py) tentar o vínculo
                    // determinístico com uma ação por tarefas.processo_sei, sem precisar
                    // parsear o número de dentro do título.
                    numeroProcesso: numeroProcesso,
                    type: 'info',
                    timestamp: new Date().toISOString(),
                    isRead: false,
                    link: '@SipacTrackingTool',
                    uid: uid
                };

                await db.collection('notificacoes').doc(notificationId).set(notificationDoc);
                console.log(`[scheduledSipacSync] Notification created: ${notificationId}`);
            } else {
                console.log(`[scheduledSipacSync] No changes for process ${numeroProcesso}.`);
            }
        } catch (e) {
            console.error(`[scheduledSipacSync] Error processing ${numeroProcesso}:`, e);
        }
    }
    return null;
});

// ─────────────────────────────────────────────────────────────────────────────
// extractDocumentTextForVoice — Lê o conteúdo bruto de um arquivo no Drive e
// retorna o texto extraído para ser injetado no contexto do copiloto de voz.
// Autenticação: Bearer token Firebase Auth.
// ─────────────────────────────────────────────────────────────────────────────
exports.extractDocumentTextForVoice = functions.runWith({
    timeoutSeconds: 120,
    memory: '512MB'
}).https.onRequest((req, res) => {
    res.set('Access-Control-Allow-Origin', '*');
    res.set('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.set('Access-Control-Allow-Headers', 'Authorization, Content-Type');

    if (req.method === 'OPTIONS') return res.status(204).send('');
    if (req.method !== 'POST') return res.status(405).json({ error: 'Método não permitido.' });

    const authHeader = req.headers['authorization'] || '';
    if (!authHeader.startsWith('Bearer ')) {
        return res.status(401).json({ error: 'Token de autenticação ausente.' });
    }

    const idToken = authHeader.slice(7);

    return admin.auth().verifyIdToken(idToken).then(async () => {
        const { driveFileId, fileName } = req.body || {};
        if (!driveFileId) {
            return res.status(400).json({ error: 'driveFileId é obrigatório.' });
        }

        try {
            const auth = await getGoogleAuth();
            const drive = google.drive({ version: 'v3', auth });

            // Fetch metadata
            const meta = await drive.files.get({
                fileId: driveFileId,
                fields: 'name,mimeType,size'
            });
            const mimeType = meta.data.mimeType || 'application/octet-stream';
            const realName = meta.data.name || fileName || 'documento';

            // Google Workspace docs → export as plain text
            const GAPPS_EXPORT_MAP = {
                'application/vnd.google-apps.document': 'text/plain',
                'application/vnd.google-apps.spreadsheet': 'text/csv',
                'application/vnd.google-apps.presentation': 'text/plain',
            };

            let textContent = '';

            if (GAPPS_EXPORT_MAP[mimeType]) {
                const exportMime = GAPPS_EXPORT_MAP[mimeType];
                const exportRes = await drive.files.export(
                    { fileId: driveFileId, mimeType: exportMime },
                    { responseType: 'arraybuffer' }
                );
                textContent = Buffer.from(exportRes.data).toString('utf-8').slice(0, 150000);
            } else if (mimeType === 'text/plain' || mimeType === 'text/csv' ||
                       realName.endsWith('.txt') || realName.endsWith('.csv') ||
                       realName.endsWith('.md')) {
                // Plain text files — download directly
                const dlRes = await drive.files.get(
                    { fileId: driveFileId, alt: 'media' },
                    { responseType: 'arraybuffer' }
                );
                textContent = Buffer.from(dlRes.data).toString('utf-8').slice(0, 150000);
            } else {
                // PDF, DOCX, XLSX e outros formatos binários:
                // Baixa os bytes do Drive e usa Gemini inline data para extrair o texto.
                const dlRes = await drive.files.get(
                    { fileId: driveFileId, alt: 'media' },
                    { responseType: 'arraybuffer' }
                );
                const fileBytes = Buffer.from(dlRes.data);
                const base64Data = fileBytes.toString('base64');

                // Busca a chave Gemini no Firestore (mesmo padrão das Cloud Functions Python)
                const keysDoc = await db.collection('system').doc('api_keys').get();
                const geminiKey = keysDoc.exists ? keysDoc.data().gemini_api_key : null;

                if (geminiKey && base64Data.length > 0) {
                    try {
                        const documentExtractionModel = 'gemini-3.5-flash-lite';
                        const geminiRes = await axios.post(
                            `https://generativelanguage.googleapis.com/v1beta/models/${documentExtractionModel}:generateContent?key=${geminiKey}`,
                            {
                                contents: [{
                                    parts: [
                                        {
                                            text: 'Extraia todo o texto deste documento de forma estruturada. Preserve títulos, listas e tabelas em Markdown quando possível. Retorne apenas o texto extraído, sem comentários ou introduções.'
                                        },
                                        {
                                            inlineData: {
                                                mimeType: mimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                                                    ? 'application/pdf' // Gemini não suporta docx inline — pode não funcionar perfeitamente
                                                    : mimeType,
                                                data: base64Data
                                            }
                                        }
                                    ]
                                }],
                                generationConfig: { maxOutputTokens: 8192 }
                            },
                            { headers: { 'Content-Type': 'application/json' }, timeout: 90000 }
                        );
                        textContent = (geminiRes.data?.candidates?.[0]?.content?.parts || [])
                            .map(part => part?.text || '')
                            .join('')
                            .trim();
                    } catch (geminiErr) {
                        console.error('Erro ao extrair texto via Gemini:', geminiErr?.response?.data || geminiErr.message);
                        textContent = `[O usuário tentou enviar o arquivo "${realName}", mas houve uma falha técnica ao ler o conteúdo do documento. Informe o usuário que não foi possível ler o arquivo neste momento.]`;
                    }
                } else {
                    textContent = `[O usuário enviou o arquivo "${realName}", mas o conteúdo está indisponível.]`;
                }
            }

            return res.status(200).json({
                text: textContent,
                fileName: realName,
                mimeType,
                driveFileId
            });
        } catch (err) {
            console.error('Erro em extractDocumentTextForVoice:', err);
            return res.status(500).json({ error: err.message });
        }
    }).catch(() => {
        return res.status(401).json({ error: 'Token inválido.' });
    });
});
