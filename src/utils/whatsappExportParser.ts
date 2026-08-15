/**
 * Utilitário para interpretar e estruturar arquivos .txt de histórico exportados do WhatsApp.
 * Suporta formatos padrão do WhatsApp em português (Android e iOS):
 * - "DD/MM/AAAA HH:MM - Autor: Mensagem"
 * - "DD/MM/YY, HH:MM:SS - Autor: Mensagem"
 * - "[DD/MM/AAAA, HH:MM:SS] Autor: Mensagem"
 * - Mensagens com múltiplas linhas e mensagens de mídia/anexo.
 */

export interface ParsedWhatsappMessage {
    id: string;
    wa_message_id: string;
    chat_id: string;
    chat_name: string;
    is_group: boolean;
    author_name: string;
    from_me: boolean;
    timestamp: Date;
    message_type: string;
    content: string;
    links: string[];
    transcription_text: null;
    transcription_model: null;
}

const normalizeStr = (s: string): string =>
    (s || '')
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .trim();

const hashStr = (str: string): string => {
    let h = 0;
    for (let i = 0; i < str.length; i++) {
        h = ((h << 5) - h) + str.charCodeAt(i);
        h |= 0;
    }
    return Math.abs(h).toString(36);
};

const URL_REGEX = /(https?:\/\/[^\s]+)/g;

function parseDateComponents(dateStr: string, timeStr: string): Date | null {
    try {
        const dParts = dateStr.split(/[\/\-\.]/).map(p => parseInt(p, 10));
        if (dParts.length !== 3) return null;
        let [day, month, year] = dParts;
        if (year < 100) {
            year += 2000;
        }

        const tParts = timeStr.split(':').map(p => parseInt(p, 10));
        if (tParts.length < 2) return null;
        const [hour, minute] = tParts;
        const second = tParts[2] || 0;

        const d = new Date(year, month - 1, day, hour, minute, second);
        return isNaN(d.getTime()) ? null : d;
    } catch {
        return null;
    }
}

function detectMessageType(content: string): string {
    if (content.includes('<Mídia oculta>') || content.includes('<Arquivo de mídia oculto>')) {
        return 'image';
    }
    if (/\.(opus|mp3|m4a|ogg|wav|aac)\s*\(arquivo anexado\)/i.test(content)) {
        return 'audio';
    }
    if (/\.(jpg|jpeg|png|webp|gif|mp4|mov|avi)\s*\(arquivo anexado\)/i.test(content)) {
        return 'image';
    }
    if (/\.(pdf|docx?|xlsx?|pptx?|txt|zip|rar|7z)\s*\(arquivo anexado\)/i.test(content)) {
        return 'document';
    }
    if (/\.vcf\s*\(arquivo anexado\)/i.test(content)) {
        return 'vcard';
    }
    return 'chat';
}

export function parseWhatsappExportTxt(
    rawText: string,
    chatId: string,
    chatName: string,
    isGroup: boolean,
    myUserName: string = 'André Martini'
): ParsedWhatsappMessage[] {
    if (!rawText || !chatId) return [];

    const normMyName = normalizeStr(myUserName);

    // Regex para padrão com traço (Android / padrão web):
    // 22/06/2023 11:34 - Nome: Mensagem
    // 22/06/23, 11:34:00 - Nome: Mensagem
    const dashMsgRegex = /^(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})[,\s]+(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(.+?):\s*(.*)$/;
    const dashSysRegex = /^(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})[,\s]+(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(.*)$/;

    // Regex para padrão entre colchetes (iOS):
    // [22/06/2023, 11:34:00] Nome: Mensagem
    const bracketMsgRegex = /^\[(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})[,\s]+(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.+?):\s*(.*)$/;
    const bracketSysRegex = /^\[(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})[,\s]+(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.*)$/;

    const lines = rawText.split(/\r?\n/);
    const parsed: ParsedWhatsappMessage[] = [];
    let current: {
        dateStr: string;
        timeStr: string;
        author: string;
        contentLines: string[];
    } | null = null;

    const flushCurrent = () => {
        if (!current) return;
        const fullContent = current.contentLines.join('\n').trim();
        if (!fullContent && current.contentLines.length === 0) return;

        const dateObj = parseDateComponents(current.dateStr, current.timeStr);
        if (!dateObj) return;

        const normAuthor = normalizeStr(current.author);
        const fromMe =
            normAuthor === normMyName ||
            normAuthor === 'eu' ||
            normAuthor === 'voce' ||
            normAuthor === 'voce';

        const authorName = fromMe ? 'Eu' : (current.author || 'Desconhecido');
        const tsMs = dateObj.getTime();
        const msgType = detectMessageType(fullContent);
        const links = (fullContent.match(URL_REGEX) || []).map(l => l.trim());

        // ID determinístico para idempotência
        const hashSeed = `${current.author}_${tsMs}_${fullContent.slice(0, 80)}`;
        const docId = `${chatId}_txt_${tsMs}_${hashStr(hashSeed)}`;
        const waMsgId = `txt_${tsMs}_${hashStr(hashSeed)}`;

        parsed.push({
            id: docId,
            wa_message_id: waMsgId,
            chat_id: chatId,
            chat_name: chatName,
            is_group: isGroup,
            author_name: authorName,
            from_me: fromMe,
            timestamp: dateObj,
            message_type: msgType,
            content: fullContent,
            links,
            transcription_text: null,
            transcription_model: null
        });
    };

    for (let i = 0; i < lines.length; i++) {
        // Limpa caracteres de controle invisíveis inseridos pelo WhatsApp
        const clean = lines[i].replace(/[\u200e\u200f\u202a-\u202e]/g, '').replace(/\u202f/g, ' ').trimEnd();

        // Testa formato com traço
        let match = dashMsgRegex.exec(clean);
        if (match) {
            flushCurrent();
            current = {
                dateStr: match[1],
                timeStr: match[2],
                author: match[3].trim(),
                contentLines: [match[4]]
            };
            continue;
        }

        // Testa formato com colchetes
        match = bracketMsgRegex.exec(clean);
        if (match) {
            flushCurrent();
            current = {
                dateStr: match[1],
                timeStr: match[2],
                author: match[3].trim(),
                contentLines: [match[4]]
            };
            continue;
        }

        // Testa mensagem de sistema (ignora do histórico de chat do usuário)
        if (dashSysRegex.test(clean) || bracketSysRegex.test(clean)) {
            flushCurrent();
            current = null;
            continue;
        }

        // Continuação de mensagem multi-linha
        if (current) {
            current.contentLines.push(clean);
        }
    }

    flushCurrent();
    return parsed;
}
