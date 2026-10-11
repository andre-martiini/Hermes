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
export function criarRecuperadorDePagina({ destruir, abrir, prazoDestruirMs = 15_000, log = console }) {
    let recuperando = false;

    async function recuperar(origem) {
        if (recuperando) return false;
        recuperando = true;
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
        liberar: () => { recuperando = false; },
        get recuperando() { return recuperando; },
    };
}
