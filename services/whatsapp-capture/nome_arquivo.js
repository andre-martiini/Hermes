// Nome original do arquivo de uma mídia (documento enviado/recebido).
//
// O avaliador de cumprimento de compromissos (functions/autonomy/cumprimento.py)
// só confere o objeto prometido ("te mando o relatório") contra o nome do anexo.
// whatsapp-web.js entrega o nome em `media.filename` (só documentos); sem ele a
// sombra de cumprimento nunca consegue medir o A06 real. O nome é aparado, sem
// caracteres de controle e limitado a 255 caracteres; vazio/ausente vira `null`.

const LIMITE = 255;
// Controles C0/C1, separadores de linha/parágrafo, marcas bidi e invisíveis
// (zero-width, BOM): evitam nome visualmente falsificado ou "vazio".
const INVISIVEIS = /[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u2028-\u202e\u2060-\u2069\ufeff]/g;

/**
 * @param {unknown} filename valor bruto de `media.filename`
 * @returns {string|null}
 */
export function nomeArquivoMidia(filename) {
    if (typeof filename !== 'string') return null;
    const limpo = filename.replace(INVISIVEIS, ' ').replace(/[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/g, '\ufffd').trim();
    if (!limpo) return null;
    return Array.from(limpo).slice(0, LIMITE).join('');
}
