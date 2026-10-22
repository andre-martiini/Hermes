// Monta o documento de uma reação (evento `message_reaction` do whatsapp-web.js) para
// `whatsapp_reactions`. Coleção própria, não `whatsapp_messages`: uma reação não é mensagem
// e não pode cair nos detectores do backend (promessa cumprida, atenção, transcrição).
//
// Um documento por pessoa e mensagem reagida: trocar o emoji sobrescreve, e tirar a reação
// grava `emoji` vazio (`removida`), em vez de apagar.

const serial = (v) => String(v?._serialized || v || '');

export function montarReacao(reacao, idsDoDono = new Set()) {
    const alvo = reacao?.msgId;
    const chatId = serial(alvo?.remote);
    const msgId = String(alvo?.id || '');
    const remetente = serial(reacao?.senderId);
    if (!chatId || !msgId || !remetente) return null;

    const emoji = String(reacao.reaction || '');
    const ts = Number(reacao.timestamp) || 0;
    return {
        id: `${chatId}_${msgId}_${remetente}`.replace(/\//g, '_'),
        dados: {
            chat_id: chatId,
            // Mesmo formato do id em whatsapp_messages (`${chatId}_${message.id.id}`).
            reacted_doc_id: `${chatId}_${msgId}`,
            reacted_wa_message_id: msgId,
            reacted_from_me: alvo.fromMe === true,
            sender_id: remetente,
            from_me: reacao.id?.fromMe === true || idsDoDono.has(remetente),
            emoji,
            removida: emoji === '',
            // O WhatsApp manda segundos ou milissegundos conforme a versão.
            reacted_at_ms: ts > 1e12 ? ts : ts * 1000,
        },
    };
}
