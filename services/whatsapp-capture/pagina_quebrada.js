// Página do WhatsApp Web quebrada: reconhecer e recriar.
//
// Em 11/10/2026 dois envios falharam com "Attempted to use detached Frame": a
// página recarregou por baixo do puppeteer e o frame antigo ficou desanexado.
// Nada recriava a página — `isClientReady` seguia true, o heartbeat dizia
// `ready: true` e todo envio/sync falhava igual até um reinício manual.

const SINAIS = [
    /detached Frame/i,
    /Execution context was destroyed/i,
    /Target closed/i,
    /Session closed/i,
    // "Protocol error (...): Target closed / Session closed / No target with given id".
    // Só "Protocol error" sem Target/Session pode ser outra coisa (argumento inválido).
    /Protocol error.*\b(Target|Session)\b/i,
];

export function ehPaginaQuebrada(erro) {
    const msg = erro?.message || String(erro ?? '');
    return SINAIS.some((re) => re.test(msg));
}

// Várias detecções juntas (o resto do lote de envio, o sync de chats) disparam
// uma recuperação só. A trava sai no próximo 'ready' (`liberar`); se abrir
// falhar, o inicializador já tenta de novo sozinho, então não precisa soltar antes.
//
// Intervalo mínimo entre recuperações: se a página quebrar de novo logo depois de
// reabrir, recriar sem pausa viraria um loop. Dentro do intervalo, a recuperação
// fica agendada para quando ele vencer (uma só).
export function criarRecuperadorDePagina({
    destruir, abrir, prazoDestruirMs = 15_000, intervaloMinimoMs = 5 * 60_000,
    agora = Date.now, agendar = setTimeout, log = console,
}) {
    let recuperando = false;
    let ultimaMs = -Infinity;
    let geracao = 0;  // `liberar` invalida uma recuperação adiada que ainda não rodou

    async function recuperar(origem) {
        if (recuperando) return false;
        recuperando = true;
        const falta = ultimaMs + intervaloMinimoMs - agora();
        if (falta > 0) {
            log.warn(`[Pagina] Página quebrada de novo (${origem}); recrio em ${Math.round(falta / 1000)}s.`);
            const minha = geracao;
            agendar(() => {
                if (minha !== geracao) return;  // a página voltou antes: não derrubar
                recuperando = false;
                recuperar(`${origem}, adiada`);
            }, falta);
            return false;
        }
        ultimaMs = agora();
        log.warn(`[Pagina] Página do WhatsApp Web quebrada (${origem}); recriando.`);
        try {
            // Best-effort e com prazo: com a página morta o destroy pode travar.
            await Promise.race([
                destruir(),
                new Promise((resolve) => setTimeout(resolve, prazoDestruirMs).unref?.()),
            ]);
        } catch (e) {
            log.error('[Pagina] Falha ao fechar o navegador quebrado:', e?.message || e);
        }
        await abrir('recuperacao_pagina');
        return true;
    }

    return {
        recuperar,
        liberar: () => { recuperando = false; geracao += 1; },
        get recuperando() { return recuperando; },
    };
}

// Envio interrompido pela página quebrada tem entrega incerta: o WhatsApp pode
// ter aceitado a mensagem antes de o puppeteer perder o frame. Antes de reenviar,
// procura a mesma mensagem já enviada na conversa (fromMe, mesmo texto, depois
// do início da tentativa) — reenviar sem conferir duplicaria para o contato.
// A folga só cobre o arredondamento do timestamp do WhatsApp (segundos) e um
// relógio levemente adiantado: mensagem igual enviada ANTES da tentativa (um
// "OK" de um minuto atrás) não pode passar por esta (achado do Codex, PR #426).
export function jaFoiEnviada(mensagens, conteudo, desdeMs, folgaMs = 2_000) {
    const alvo = String(conteudo ?? '').trim();
    return (mensagens || []).find((m) => m?.fromMe
        && String(m.body ?? '').trim() === alvo
        && Number(m.timestamp) * 1000 >= desdeMs - folgaMs) || null;
}
