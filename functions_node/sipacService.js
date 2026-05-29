const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const axios = require('axios');
const os = require('os');
const { load } = require('cheerio');

try {
    puppeteer.use(StealthPlugin());
} catch (e) {
    // Already in use or error
}

const SIPAC_BASE_URL = 'https://sipac.ifes.edu.br';
const SIPAC_PORTAL_URL = `${SIPAC_BASE_URL}/public/jsp/portal.jsf`;
const SIPAC_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT; Windows NT 10.0; pt-BR) WindowsPowerShell/5.1.26100.4202'
];

function buildSIPACHeaders(userAgent, extraHeaders = {}) {
    return {
        'user-agent': userAgent,
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.7,en;q=0.6',
        ...extraHeaders
    };
}

function createCookieJar() {
    return new Map();
}

function updateCookieJar(cookieJar, response) {
    const cookies = typeof response?.headers?.getSetCookie === 'function'
        ? response.headers.getSetCookie()
        : [];

    for (const rawCookie of cookies) {
        const firstPart = String(rawCookie || '').split(';')[0];
        const separator = firstPart.indexOf('=');
        if (separator <= 0) continue;
        cookieJar.set(firstPart.slice(0, separator).trim(), firstPart.slice(separator + 1).trim());
    }
}

function serializeCookies(cookieJar) {
    return Array.from(cookieJar.entries()).map(([name, value]) => `${name}=${value}`).join('; ');
}

function isCaptchaResponse(response, html) {
    const finalUrl = String(response?.url || '');
    const body = String(html || '');
    return finalUrl.includes('validate.perfdrive.com') ||
        /radware captcha page/i.test(body) ||
        /we apologize for the inconvenience/i.test(body) ||
        /request unblock to the website/i.test(body);
}

async function openSIPACPortalSession() {
    for (const userAgent of SIPAC_USER_AGENTS) {
        const cookieJar = createCookieJar();
        try {
            const response = await fetch(SIPAC_PORTAL_URL, {
                headers: buildSIPACHeaders(userAgent),
                redirect: 'follow'
            });
            updateCookieJar(cookieJar, response);
            const html = await response.text();

            if (!isCaptchaResponse(response, html) && html.includes('id="processoForm"')) {
                return { html, userAgent, cookieJar };
            }
        } catch (e) {
            console.error(`[SIPAC] Failed to open portal with UA ${userAgent}:`, e.message);
        }
    }

    throw new Error('SIPAC anti-bot bloqueou a consulta publica.');
}

async function fetchSIPACText(url, context, options = {}) {
    const headers = buildSIPACHeaders(context.userAgent, options.headers || {});
    const cookieHeader = serializeCookies(context.cookieJar);
    if (cookieHeader) headers.cookie = cookieHeader;

    const response = await fetch(url, {
        redirect: 'follow',
        ...options,
        headers
    });

    updateCookieJar(context.cookieJar, response);
    const html = await response.text();

    if (isCaptchaResponse(response, html)) {
        throw new Error('SIPAC anti-bot bloqueou a consulta publica.');
    }

    return { response, html };
}

function normalizeWhitespace(value) {
    return String(value || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
}

function normalizeTitle(value) {
    return String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toUpperCase()
        .replace(/[^A-Z0-9]/g, '');
}

function escapeRegExp(value) {
    return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function toAbsoluteSIPACUrl(url) {
    if (!url) return '';
    if (url.startsWith('http')) return url;
    return SIPAC_BASE_URL + (url.startsWith('/') ? '' : '/') + url;
}

function extractUrlFromOnclick(onclick) {
    const rawOnclick = String(onclick || '');
    const openMatch = rawOnclick.match(/window\.open\('([^']+)'/i);
    if (openMatch?.[1]) return openMatch[1];

    const detailMatch = rawOnclick.match(/(\/[^'"]*processo_detalhado[^'"]*)/i);
    if (detailMatch?.[1]) return detailMatch[1];

    const processIdMatch = rawOnclick.match(/detalhar\((\d+)\)/i);
    if (processIdMatch?.[1]) return `/public/jsp/processos/processo_detalhado.jsf?id=${processIdMatch[1]}`;

    const documentIdMatch = rawOnclick.match(/documentoPublicoDetalhado\((\d+)\)/i);
    if (documentIdMatch?.[1]) return `/public/jsp/processos/documento_visualizacao.jsf?idDoc=${documentIdMatch[1]}`;

    return '';
}

function getDirectRows($, $table) {
    const rows = [];
    ['thead', 'tbody', 'tfoot'].forEach((sectionName) => {
        $table.children(sectionName).each((_, section) => {
            rows.push(...$(section).children('tr').toArray());
        });
    });

    if (rows.length === 0) {
        rows.push(...$table.children('tr').toArray());
    }

    return rows;
}

function findProcessDetailUrl(html) {
    const $ = load(html);
    const candidates = $('a[href], a[onclick], img[onclick]').toArray();

    for (const element of candidates) {
        const $element = $(element);
        const href = $element.attr('href') || '';
        const onclick = $element.attr('onclick') || '';
        const title = ($element.attr('title') || '').toLowerCase();
        const alt = ($element.attr('alt') || '').toLowerCase();
        const text = normalizeWhitespace($element.text()).toLowerCase();

        if (
            href.includes('processo_detalhado') ||
            onclick.toLowerCase().includes('processo_detalhado') ||
            onclick.toLowerCase().includes('detalhar(') ||
            title.includes('visualizar processo') ||
            alt.includes('visualizar processo') ||
            text.includes('visualizar processo')
        ) {
            return toAbsoluteSIPACUrl(href || extractUrlFromOnclick(onclick));
        }
    }

    return '';
}

function parseListagemTable($, titleText, extractLinks = false) {
    const cleanTitle = normalizeTitle(titleText);
    const weakTitle = cleanTitle.slice(0, 8);
    const titleMatches = (text) => {
        const normalized = normalizeTitle(text);
        if (!normalized) return false;
        if (cleanTitle && normalized.includes(cleanTitle)) return true;
        if (cleanTitle && cleanTitle.includes(normalized)) return true;
        if (weakTitle.length >= 5 && normalized.includes(weakTitle)) return true;
        return false;
    };

    const table = $('table.subListagem, table.listagem').toArray().find((rawTable) => {
        const $table = $(rawTable);
        const captionText = normalizeWhitespace($table.children('caption').first().text());
        if (captionText && titleMatches(captionText)) return true;

        let previous = $table.prev();
        while (previous.length) {
            const text = normalizeWhitespace(previous.text());
            if (text && titleMatches(text)) return true;

            const tagName = String(previous.get(0)?.tagName || '').toLowerCase();
            if (tagName === 'table' || tagName === 'hr') break;
            previous = previous.prev();
        }

        return false;
    });

    if (!table) return [];

    return getDirectRows($, $(table))
        .filter((row) => {
            const $row = $(row);
            const text = normalizeWhitespace($row.text()).toUpperCase();
            if (text.includes('TIPO') && text.includes('NOME') && text.includes('IDENTIFICADOR')) return false;
            if (String($row.attr('class') || '').includes('header')) return false;
            return $row.children('td').length >= 2;
        })
        .map((row) => {
            const $row = $(row);
            const cells = $row.children('td').toArray();

            if (String(titleText || '').toUpperCase().includes('INTERESS')) {
                return {
                    tipo: normalizeWhitespace($(cells[0]).text()),
                    nome: normalizeWhitespace($(cells[2] || cells[1]).text())
                };
            }

            return cells.map((cell) => {
                const $cell = $(cell);
                if (extractLinks) {
                    const link = $cell.find('a[onclick], a[href]').first();
                    if (link.length) {
                        const href = link.attr('href') || '';
                        const onclick = link.attr('onclick') || '';
                        return {
                            text: normalizeWhitespace($cell.text()),
                            url: toAbsoluteSIPACUrl(href && href !== '#' ? href : extractUrlFromOnclick(onclick))
                        };
                    }
                }

                return normalizeWhitespace($cell.text());
            });
        });
}

function parseDocumentosCancelados($) {
    const table = $('table.subListagem, table.listagem').toArray().find((rawTable) => {
        const $table = $(rawTable);
        const captionText = normalizeWhitespace($table.children('caption').first().text());
        const tableText = normalizeWhitespace($table.text());
        return tableText.includes('Documentos Cancelados') || captionText.includes('Cancelados');
    });

    if (!table) return [];

    const rows = getDirectRows($, $(table));
    const results = [];

    for (let index = 0; index < rows.length; index += 1) {
        const cells = $(rows[index]).children('td').toArray();
        if (cells.length < 5) continue;

        const record = {
            numeroDocumento: normalizeWhitespace($(cells[0]).text()),
            tipoDocumento: normalizeWhitespace($(cells[1]).text()),
            usuarioSolicitacao: normalizeWhitespace($(cells[2]).text()),
            dataSolicitacao: normalizeWhitespace($(cells[3]).text()),
            usuarioCancelamento: normalizeWhitespace($(cells[4]).text()),
            dataCancelamento: normalizeWhitespace($(cells[5]).text()),
            justificativa: ''
        };

        const nextRowText = normalizeWhitespace($(rows[index + 1]).text());
        if (nextRowText.includes('Justificativa:')) {
            record.justificativa = nextRowText.replace(/Justificativa:\s*/i, '').trim();
            index += 1;
        }

        results.push(record);
    }

    return results;
}

function getCellText(value) {
    return typeof value === 'object' && value !== null ? value.text : value;
}

function getTextFromDetailPage($, label) {
    const normalizedLabel = normalizeWhitespace(label).toUpperCase();
    const cells = $('td, th').toArray();

    let targetCell = cells.find((cell) => normalizeWhitespace($(cell).text()).toUpperCase() === normalizedLabel);
    if (!targetCell) {
        targetCell = cells.find((cell) => normalizeWhitespace($(cell).text()).toUpperCase().startsWith(normalizedLabel));
    }

    if (targetCell) {
        const $targetCell = $(targetCell);
        const nextCell = $targetCell.next('td');
        if (nextCell.length) return normalizeWhitespace(nextCell.text());

        const fullText = normalizeWhitespace($targetCell.text());
        if (fullText.toUpperCase().includes(normalizedLabel)) {
            return fullText.slice(fullText.toUpperCase().indexOf(normalizedLabel) + normalizedLabel.length).replace(/^[:\s]+/, '').trim();
        }
    }

    const bodyText = normalizeWhitespace($('body').text());
    const match = bodyText.match(new RegExp(`${escapeRegExp(label)}\\s*:?\\s*(.*)`, 'i'));
    if (match?.[1]) return match[1].trim();

    return 'Não informado';
}

function parseSIPACDetailHtml(html) {
    const $ = load(html);

    const interessados = parseListagemTable($, 'INTERESSADOS')
        .map((item) => ({ tipo: item.tipo, nome: item.nome }))
        .filter((item) => item?.nome);

    const movimentacoes = parseListagemTable($, 'MOVIMENTACOES')
        .filter((row) => row.length >= 6)
        .map((row) => {
            const sentDate = String(row[0] || '').split(' ');
            const receivedDate = String(row[4] || '').split(' ');
            return {
                data: sentDate[0] || '',
                horario: sentDate[1] || '',
                unidadeOrigem: row[1] || '',
                unidadeDestino: row[2] || '',
                usuarioRemetente: row[3] || '',
                dataRecebimento: receivedDate[0] || '',
                horarioRecebimento: receivedDate[1] || '',
                usuarioRecebedor: row[5] || '',
                urgente: row[6] || 'Não'
            };
        })
        .filter((item) =>
            /^\d{2}\/\d{2}\/\d{4}$/.test(String(item.data || '').trim()) &&
            String(item.unidadeOrigem || '').trim() !== '' &&
            String(item.unidadeDestino || '').trim() !== ''
        );

    const documentos = [];
    const seenDocuments = new Set();

    parseListagemTable($, 'DOCUMENTOS DO PROCESSO', true)
        .filter((row) => {
            const ordem = String(getCellText(row[0]) || '').trim();
            const dataDocumento = String(getCellText(row[2]) || '').trim();
            return row.length >= 5 && /^\d+$/.test(ordem) && /^\d{2}\/\d{2}\/\d{4}$/.test(dataDocumento);
        })
        .forEach((row) => {
            const linkColumn = row.find((column) => typeof column === 'object' && column.url);
            const documentRecord = {
                ordem: getCellText(row[0]),
                tipo: getCellText(row[1]),
                data: getCellText(row[2]),
                unidadeOrigem: getCellText(row[3]),
                natureza: getCellText(row[4]),
                statusVisualizacao: 'Identificado',
                url: linkColumn ? linkColumn.url : ''
            };

            const key = `${documentRecord.ordem}|${documentRecord.tipo}|${documentRecord.data}`;
            if (seenDocuments.has(key)) return;
            seenDocuments.add(key);
            documentos.push(documentRecord);
        });

    let unidadeAtual = getTextFromDetailPage($, 'Unidade de Origem:');
    if (movimentacoes.length > 0) {
        unidadeAtual = movimentacoes[movimentacoes.length - 1].unidadeDestino;
    }

    return {
        numeroProcesso: getTextFromDetailPage($, 'Processo:').split('\n')[0].trim(),
        dataAutuacion: getTextFromDetailPage($, 'Data de Autuação:').split(' ')[0],
        horarioAutuacion: getTextFromDetailPage($, 'Data de Autuação:').split(' ')[1] || '',
        usuarioAutuacion: getTextFromDetailPage($, 'Usuário de Autuação:'),
        natureza: getTextFromDetailPage($, 'Natureza do Processo:'),
        status: getTextFromDetailPage($, 'Status:'),
        dataCadastro: getTextFromDetailPage($, 'Data de Cadastro:'),
        unidadeOrigem: getTextFromDetailPage($, 'Unidade de Origem:'),
        unidadeAtual,
        totalDocumentos: String(documentos.length),
        observacao: getTextFromDetailPage($, 'Observação:'),
        assuntoCodigo: getTextFromDetailPage($, 'Assunto do Processo:').split(' - ')[0],
        assuntoDescricao: getTextFromDetailPage($, 'Assunto do Processo:').split(' - ').slice(1).join(' - '),
        assuntoDetalhado: getTextFromDetailPage($, 'Assunto Detalhado:'),
        interessados,
        documentos,
        movimentacoes,
        incidentes: parseDocumentosCancelados($)
    };
}

function getPuppeteerLaunchOptions() {
    const executableCandidates = [
        process.env.PUPPETEER_EXECUTABLE_PATH,
        process.env.CHROME_PATH,
        process.env.EDGE_PATH,
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
        'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
        '/usr/bin/google-chrome',
        '/usr/bin/chromium-browser',
        '/usr/bin/chromium',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
    ].filter(Boolean);

    const executablePath = executableCandidates.find(candidate => fs.existsSync(candidate));

    return {
        headless: "new",
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
        ...(executablePath ? { executablePath } : {})
    };
}

function generateSnapshotHash(data) {
    const relevantContent = {
        status: data.status,
        unidadeAtual: data.unidadeAtual,
        movimentacoesCount: data.movimentacoes?.length,
        documentosCount: data.documentos?.length,
        ultimaMovimentacao: data.movimentacoes?.[data.movimentacoes.length - 1]?.data || '',
        assuntoDetalhado: data.assuntoDetalhado
    };
    return crypto.createHash('md5').update(JSON.stringify(relevantContent)).digest('hex');
}

async function scrapeSIPACProcessBrowser(protocol) {
    console.log(`[SIPAC] Starting browser fallback scraper for ${protocol}...`);
    const browser = await puppeteer.launch(getPuppeteerLaunchOptions());

    try {
        const page = await browser.newPage();
        await page.setDefaultNavigationTimeout(60000);
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

        await page.setRequestInterception(true);
        page.on('request', (req) => {
            if (['image', 'font', 'media'].includes(req.resourceType())) {
                req.abort();
            } else {
                req.continue();
            }
        });

        console.log(`[SIPAC] Opening portal (browser)...`);
        await page.goto('https://sipac.ifes.edu.br/public/jsp/portal.jsf', { waitUntil: 'networkidle2', timeout: 90000 });

        const hasSearchForm = async () => page.evaluate(() =>
            !!document.querySelector('form#processoForm input[name="RADICAL_PROTOCOLO"], form#processoForm input[name="NUM_PROTOCOLO"]')
        );

        let searchPageReady = await hasSearchForm();

        if (!searchPageReady) {
            console.log('[SIPAC] Search form not loaded. Attempting menu fallback...');
            await page.evaluate(() => {
                const el = document.querySelector('div#l-processos') ||
                    Array.from(document.querySelectorAll('span, div, a')).find(e => e.innerText.trim() === 'Processos');
                if (el) el.click();
            });

            await page.waitForSelector('input[name*="RADICAL_PROTOCOLO"]', { timeout: 15000 }).catch(() => null);
            searchPageReady = await hasSearchForm();
        }

        if (!searchPageReady) {
            throw new Error('Falha ao inicializar formulário de busca no browser.');
        }

        console.log(`[SIPAC] Preparing search form (browser)...`);
        await page.evaluate(() => {
            const radio = document.querySelector('form#processoForm #n_proc_p');
            if (radio) {
                radio.click();
                radio.checked = true;
                if (typeof window.divProcessoP === 'function') window.divProcessoP(true);
            }
        });

        const parts = protocol.match(/(\d{5})[.\s]*(\d{6})[/\s]*(\d{4})[- \s]*(\d{2})/);
        if (!parts) throw new Error('Formato de protocolo inválido. Use XXXXX.XXXXXX/XXXX-XX');

        await page.evaluate((p) => {
            const form = document.querySelector('form#processoForm');
            const findInput = (namePart) => Array.from(form?.querySelectorAll('input') || []).find(i => i.name && i.name.includes(namePart));
            const fields = {
                'RADICAL_PROTOCOLO': p[1], 'NUM_PROTOCOLO': p[2], 'ANO_PROTOCOLO': p[3], 'DV_PROTOCOLO': p[4]
            };
            for (const [name, value] of Object.entries(fields)) {
                const input = findInput(name);
                if (input) {
                    input.value = value;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.dispatchEvent(new Event('blur', { bubbles: true }));
                }
            }
        }, parts);

        console.log(`[SIPAC] Clicking 'Consultar' (browser)...`);
        const clickedConsultar = await page.evaluate(() => {
            const form = document.querySelector('form#processoForm');
            const submitBtn = Array.from(form?.querySelectorAll('input[type="submit"]') || []).find(b =>
                (b.value || '').toLowerCase().includes('consultar')
            );
            if (submitBtn) {
                submitBtn.click();
                return true;
            }
            if (form && typeof form.submit === 'function') {
                form.submit();
                return true;
            }
            return false;
        });

        if (!clickedConsultar) throw new Error('Falha ao acionar consulta no SIPAC.');

        await Promise.race([
            page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 45000 }).catch(() => null),
            page.waitForSelector('img[title*="Visualizar"], img[alt*="Visualizar"], a[id*="detalhar"], a[href*="processo_detalhado"]', { timeout: 45000 }).catch(() => null),
            page.waitForFunction(() => {
                const text = (document.body?.innerText || '').toLowerCase();
                return text.includes('nenhum processo foi encontrado');
            }, { timeout: 45000 }).catch(() => null)
        ]);

        console.log(`[SIPAC] Checking results (browser)...`);
        const detailUrl = await page.evaluate(() => {
            const SIPAC_DOMAIN = 'https://sipac.ifes.edu.br';
            const toAbs = (url) => {
                if (!url) return '';
                if (url.startsWith('http')) return url;
                return SIPAC_DOMAIN + (url.startsWith('/') ? '' : '/') + url;
            };

            const extractUrlFromOnclick = (onclick) => {
                if (!onclick) return '';
                const openMatch = onclick.match(/window\.open\('([^']+)'/i);
                if (openMatch?.[1]) return openMatch[1];
                const detailMatch = onclick.match(/(\/[^'"]*processo_detalhado[^'"]*)/i);
                if (detailMatch?.[1]) return detailMatch[1];
                const idMatch = onclick.match(/detalhar\((\d+)\)/i);
                if (idMatch?.[1]) return `/public/jsp/processos/processo_detalhado.jsf?id=${idMatch[1]}`;
                return '';
            };

            const candidates = Array.from(document.querySelectorAll('a[href], a[onclick], img[onclick]'));
            for (const el of candidates) {
                const href = el.getAttribute('href') || '';
                const onclick = el.getAttribute('onclick') || '';
                const title = (el.getAttribute('title') || '').toLowerCase();
                const alt = (el.getAttribute('alt') || '').toLowerCase();
                const text = (el.textContent || '').toLowerCase();

                if (
                    href.includes('processo_detalhado') ||
                    onclick.toLowerCase().includes('processo_detalhado') ||
                    onclick.toLowerCase().includes('detalhar(') ||
                    title.includes('visualizar processo') ||
                    alt.includes('visualizar processo') ||
                    text.includes('visualizar processo')
                ) {
                    const resolved = href || extractUrlFromOnclick(onclick);
                    if (resolved) return toAbs(resolved);
                }
            }
            return '';
        });

        if (!detailUrl) {
            const noResults = await page.evaluate(() => (document.body?.innerText || '').includes('Nenhum processo foi encontrado'));
            if (noResults) throw new Error('Nenhum processo foi encontrado com este numero/ano.');
            throw new Error('Falha ao localizar resultado na tabela do SIPAC.');
        }

        console.log(`[SIPAC] Opening process detail page (browser)...`);
        await page.goto(detailUrl, { waitUntil: 'networkidle2', timeout: 120000 });

        const detailHtml = await page.content();
        const result = parseSIPACDetailHtml(detailHtml);
        result.detailUrl = detailUrl;
        result.totalDocumentos = result.documentos.length.toString();
        result.snapshot_hash = generateSnapshotHash(result);
        result.scraping_last_error = null;

        return result;

    } catch (error) {
        console.error('[SIPAC BROWSER SCRAPER ERROR]', error);
        throw error;
    } finally {
        await browser.close();
    }
}

async function scrapeSIPACProcess(protocol) {
    try {
        const parts = protocol.match(/(\d{5})[.\s]*(\d{6})[/\s]*(\d{4})[- \s]*(\d{2})/);
        console.log(`[SIPAC] Starting HTTP scraper for ${protocol}...`);
        if (!parts) throw new Error('Formato de protocolo inválido. Use XXXXX.XXXXXX/XXXX-XX');

        console.log(`[SIPAC] Opening portal...`);
        const session = await openSIPACPortalSession();
        const context = {
            userAgent: session.userAgent,
            cookieJar: session.cookieJar
        };

        const formMatch = session.html.match(/<form[^>]*id="processoForm"[^>]*action="([^"]+)"[\s\S]*?<\/form>/i);
        if (!formMatch?.[0] || !formMatch?.[1]) {
            throw new Error('Falha ao localizar formulario publico do SIPAC.');
        }

        const hiddenInputs = Array.from(formMatch[0].matchAll(/<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"/gi));
        const submitMatch = formMatch[0].match(/<input[^>]*type="submit"[^>]*name="([^"]+)"[^>]*value="([^"]*)"/i);
        const params = new URLSearchParams();

        hiddenInputs.forEach((match) => params.set(match[1], match[2]));
        params.set('tipo_consulta', '100');
        params.set('RADICAL_PROTOCOLO', parts[1]);
        params.set('NUM_PROTOCOLO', parts[2]);
        params.set('ANO_PROTOCOLO', parts[3]);
        params.set('DV_PROTOCOLO', parts[4]);
        if (submitMatch?.[1]) {
            params.set(submitMatch[1], submitMatch[2] || 'Consultar Processo');
        }

        console.log(`[SIPAC] Submitting process search...`);
        const actionUrl = new URL(formMatch[1], SIPAC_BASE_URL).href;
        const { html: resultsHtml } = await fetchSIPACText(actionUrl, context, {
            method: 'POST',
            headers: {
                'content-type': 'application/x-www-form-urlencoded'
            },
            body: params.toString()
        });

        if (/Nenhum processo foi encontrado/i.test(resultsHtml)) {
            throw new Error('Nenhum processo foi encontrado com este numero/ano.');
        }

        console.log(`[SIPAC] Checking results...`);
        const detailUrl = findProcessDetailUrl(resultsHtml);
        if (!detailUrl) {
            throw new Error('Falha ao localizar resultado na tabela do SIPAC.');
        }

        console.log(`[SIPAC] Opening process detail page...`);
        const { html: detailHtml } = await fetchSIPACText(detailUrl, context);

        console.log(`[SIPAC] Extracting data...`);
        const result = parseSIPACDetailHtml(detailHtml);
        result.detailUrl = detailUrl;
        result.totalDocumentos = result.documentos.length.toString();
        result.snapshot_hash = generateSnapshotHash(result);
        result.scraping_last_error = null;

        return result;

    } catch (error) {
        console.warn(`[SIPAC HTTP SCRAPER FAILED] (${error.message}). Attempting browser fallback...`);
        try {
            return await scrapeSIPACProcessBrowser(protocol);
        } catch (browserError) {
            console.error('[SIPAC BOTH SCRAPERS FAILED]', browserError);
            const rawError = `${browserError?.name || ''} ${browserError?.message || ''}`.toLowerCase();
            let errorMessage = "Erro Desconhecido";

            if (browserError.message.includes('timeout')) errorMessage = "Timeout (Portal Lento)";
            if (browserError.message.includes('encontrado')) errorMessage = "Processo Não Encontrado";
            if (browserError.message.includes('formato de protocolo')) errorMessage = "Protocolo Inválido";
            if (browserError.message.includes('anti-bot') || rawError.includes('captcha') || rawError.includes('perfdrive')) errorMessage = "Bloqueado por Anti-Bot/Captcha";

            return {
                numeroProcesso: protocol,
                scraping_last_error: errorMessage,
                status: "ERRO_SCRAPING",
                interessados: [],
                documentos: [],
                movimentacoes: [],
                incidentes: []
            };
        }
    }
}

module.exports = {
    scrapeSIPACProcess
};
