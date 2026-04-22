const fs = require('fs');

const content = fs.readFileSync('functions_node/index.js', 'utf-8');

const newFunction = `
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
`;

fs.writeFileSync('functions_node/index.js', content + "\n" + newFunction);
