export type DiaryRichType = 'LINK' | 'CONTACT' | 'FILE';

interface DiaryRichPayload {
  n?: string;
  v: string;
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

export const parseDiaryRichNote = (text: string) => {
  const types: DiaryRichType[] = ['LINK', 'CONTACT', 'FILE'];

  for (const type of types) {
    const prefix = `${type}::`;
    if (!text.startsWith(prefix)) continue;

    const rawPayload = text.slice(prefix.length);
    if (rawPayload.startsWith(DIARY_JSON_PREFIX)) {
      const jsonPayload = rawPayload.slice(DIARY_JSON_PREFIX.length);
      try {
        const parsed = JSON.parse(jsonPayload) as DiaryRichPayload;
        if (typeof parsed.v === 'string') {
          return { type, name: parsed.n || '', value: parsed.v };
        }
      } catch {
        // Ignore malformed JSON and fallback to legacy parser below.
      }
    }

    const legacy = parseLegacyDiaryPayload(rawPayload);
    return { type, name: legacy.name || '', value: legacy.value || '' };
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
