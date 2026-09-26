// Abre o WhatsApp Web e, se falhar, tenta de novo sozinho.
//
// Até 25/09/2026 o boot era um `client.initialize()` solto. Quando a navegação
// até web.whatsapp.com não completa (rede ainda subindo no logon, WhatsApp Web
// lento), o puppeteer desiste depois do `protocolTimeout` (300s) com
// "Page.navigate timed out", a promessa rejeitada caía no handler de
// unhandledRejection e o worker ficava vivo mas parado: sem captura e sem envio
// até alguém reiniciá-lo à mão.
//
// Agora a falha fecha o Chromium que sobrou (senão a próxima tentativa esbarra
// no perfil do LocalAuth ainda travado) e agenda outra, com espera crescente.

export const ESPERA_INICIAL_MS = 30_000;
export const ESPERA_MAXIMA_MS = 10 * 60_000;

export function esperaDaTentativa(falhas) {
    return Math.min(ESPERA_INICIAL_MS * 2 ** Math.max(falhas - 1, 0), ESPERA_MAXIMA_MS);
}

// Avisar a cada falha seria spam num boot sem rede; nunca avisar esconde um
// worker parado. Primeira falha e depois a cada 5.
export function deveAvisar(falhas) {
    return falhas === 1 || falhas % 5 === 0;
}

export function criarInicializador({ inicializar, destruir, alertar, agendar = setTimeout, log = console }) {
    let falhas = 0;
    let emAndamento = false;

    return async function abrir(origem = 'boot') {
        if (emAndamento) return;
        emAndamento = true;
        try {
            await inicializar();
            if (falhas > 0) {
                log.log(`[Init] WhatsApp Web aberto após ${falhas} falha(s).`);
                alertar(`✅ Hermes WhatsApp: o worker conseguiu abrir o WhatsApp Web depois de ${falhas} tentativa(s) sem sucesso.`);
            }
            falhas = 0;
        } catch (erro) {
            falhas += 1;
            const espera = esperaDaTentativa(falhas);
            const motivo = erro?.message || String(erro);
            log.error(`[Init] Falha ao abrir o WhatsApp Web (${origem}, falha ${falhas}):`, erro);
            if (deveAvisar(falhas)) {
                alertar(
                    `⚠️ Hermes WhatsApp: não consegui abrir o WhatsApp Web (${motivo}). ` +
                    `Tento de novo sozinho em ${Math.round(espera / 1000)}s — falha ${falhas}. ` +
                    'Enquanto isso não há captura nem envio.'
                );
            }
            try {
                await destruir();
            } catch (e) {
                log.error('[Init] Falha ao fechar o navegador da tentativa anterior:', e?.message || e);
            }
            // `abrir` nunca rejeita (a falha cai neste catch), então a promessa
            // devolvida ao timer não vira unhandledRejection.
            agendar(() => abrir('retentativa'), espera);
        } finally {
            emAndamento = false;
        }
    };
}
