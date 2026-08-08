export type DiaryRichType = 'LINK' | 'CONTACT' | 'FILE' | 'EMAIL';

interface DiaryRichPayload {
  n?: string;
  v: string;
  s?: string; // EMAIL: remetente
  r?: string; // EMAIL: resumo gerado pela IA do que o e-mail significa para a ação
}

const DIARY_JSON_PREFIX = 'JSON::';

const parseLegacyDiaryPayload = (value: string) => {
  const separatorIndex = value.indexOf('::');
  if (separatorIndex === -1) {
    return { name: '', value };
  }

  return {
    name: value.slice(0, separatorIndex),
    value: value.slice(separatorIndex + 2)
  };
};

export const buildDiaryRichNote = (type: DiaryRichType, name: string, value: string) => {
  const payload: DiaryRichPayload = { n: name || '', v: value || '' };
  return `${type}::${DIARY_JSON_PREFIX}${JSON.stringify(payload)}`;
};

// E-mails vinculados por IA (functions/email_action_linker.py) usam campos extras
// (remetente, resumo) além de nome/valor.
export const buildDiaryEmailNote = (subject: string, sender: string, gmailUrl: string, resumo?: string) => {
  const payload: DiaryRichPayload = { n: subject || '', v: gmailUrl || '', s: sender || '', r: resumo || '' };
  return `EMAIL::${DIARY_JSON_PREFIX}${JSON.stringify(payload)}`;
};

// Nota de diário para vínculos sinal↔ação de canais sem envelope rico dedicado
// (SIPAC, Calendar, WhatsApp, ...) — mesmo formato de texto que
// functions/email_action_linker.py:_build_diary_note gera no backend, para que
// uma sugestão decidida pela fila web (DashboardView.tsx) produza a mesma nota
// que uma decidida via Telegram.
export const buildDiaryGenericNote = (icon: string, label: string, titulo: string, origem: string, resumo: string, link?: string) => {
  const lines = [`[${icon} Hermes] ${label}: ${titulo}`];
  if (origem) lines.push(origem);
  if (resumo) lines.push(resumo);
  if (link) lines.push(`Link: ${link}`);
  return lines.join('\n');
};

export const parseDiaryRichNote = (text: string) => {
  const types: DiaryRichType[] = ['LINK', 'CONTACT', 'FILE', 'EMAIL'];

  for (const type of types) {
    const prefix = `${type}::`;
    if (!text.startsWith(prefix)) continue;

    const rawPayload = text.slice(prefix.length);
    if (rawPayload.startsWith(DIARY_JSON_PREFIX)) {
      const jsonPayload = rawPayload.slice(DIARY_JSON_PREFIX.length);
      try {
        const parsed = JSON.parse(jsonPayload) as DiaryRichPayload;
        if (typeof parsed.v === 'string') {
          return { type, name: parsed.n || '', value: parsed.v, sender: parsed.s || '', resumo: parsed.r || '' };
        }
      } catch {
        // Ignore malformed JSON and fallback to legacy parser below.
      }
    }

    const legacy = parseLegacyDiaryPayload(rawPayload);
    return { type, name: legacy.name || '', value: legacy.value || '', sender: '', resumo: '' };
  }

  return null;
};

export const ensureHttpUrl = (url: string) => {
  const trimmed = (url || '').trim();
  if (!trimmed) return '';

  if (/^[a-zA-Z][a-zA-Z\d+\-.]*:/.test(trimmed)) {
    return trimmed;
  }

  return `https://${trimmed}`;
};

export const getRenamedFileName = (originalName: string, desiredName?: string) => {
  const cleanedDesiredName = (desiredName || '').trim().replace(/[\\/]/g, '-');
  if (!cleanedDesiredName) return originalName;

  const originalExtension = originalName.includes('.') ? `.${originalName.split('.').pop() || ''}` : '';
  const hasExtension = /\.[^.]+$/.test(cleanedDesiredName);

  if (!originalExtension || hasExtension) {
    return cleanedDesiredName;
  }

  return `${cleanedDesiredName}${originalExtension}`;
};
