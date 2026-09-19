// Detecção de menção ao dono numa mensagem de grupo.
//
// Desde a migração do WhatsApp para `@lid`, a menção chega com o lid do dono
// (`144...@lid`), não com o telefone (`55...@c.us`) que `client.info.wid` devolve.
// Comparar só com o telefone deixava `mentions_andre` falso em toda mensagem —
// 0 de 45 menções reais em 30 dias. Em parte delas, `mentionedIds` nem chega
// preenchido e só o corpo traz o token `@<lid>`, por isso o corpo também conta.

const soDigitos = (v) => String(v || '').replace(/[^0-9]/g, '');
const usuario = (id) => String(id || '').split('@')[0];

/** O token só vale após início de texto ou caractere que não seja letra/número (não é e-mail). `digitos` vem de `soDigitos`, sem nada a escapar. */
function tokenNoCorpo(digitos, corpo) {
    return new RegExp(`(^|[^\\p{L}\\p{N}_])@${digitos}(?![0-9])`, 'u').test(corpo);
}

/**
 * @param {{ mentionedIds?: string[], body?: string, ownIds?: Iterable<string> }} args
 *   ownIds: ids serializados do dono (`...@c.us`, `...@lid`), de qualquer origem.
 * @returns {boolean}
 */
export function detectarMencao({ mentionedIds = [], body = '', ownIds = [] } = {}) {
    const proprios = new Set([...ownIds].map((id) => String(id || '').trim()).filter(Boolean));
    if (proprios.size === 0) return false;

    if (mentionedIds.some((id) => proprios.has(String(id)))) return true;

    const corpo = String(body || '');
    if (!corpo.includes('@')) return false;
    // 8+ dígitos: descarta lixo sem risco de casar "@123" num texto qualquer.
    const usuarios = [...proprios].map((id) => soDigitos(usuario(id))).filter((d) => d.length >= 8);
    return usuarios.some((d) => tokenNoCorpo(d, corpo));
}
