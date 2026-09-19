// Opções do Puppeteer do worker e sinais que disparam o desligamento limpo.
//
// Por padrão o Puppeteer trata SIGINT/SIGTERM/SIGHUP por conta própria
// (@puppeteer/browsers, launch.js): no SIGINT ele mata o Chromium com
// `taskkill /T /F` e chama process.exit(130) na hora; em SIGTERM/SIGHUP também
// derruba o Chromium. Tudo isso acontece ANTES de `desligar()` (index.js) conseguir
// fechar o cliente, então toda parada por Ctrl+C matava o Chromium abruptamente —
// e uma parada suja do perfil do LocalAuth é o que pode obrigar a reautenticar por QR.
// Com os três desligados, o worker é o único a decidir como encerrar.

// Função (e não constante) porque o LocalAuth grava `userDataDir` no objeto que recebe.
export function criarOpcoesPuppeteer() {
    return {
        // Mídias grandes estouravam o protocolTimeout padrão (180s) do puppeteer no
        // downloadMedia ("Runtime.callFunctionOn timed out") — visto em produção.
        protocolTimeout: 300000,
        handleSIGINT: false,
        handleSIGTERM: false,
        handleSIGHUP: false,
    };
}

// SIGBREAK (Ctrl+Break) só existe no Windows; em outras plataformas o Node aceita
// o listener e ele simplesmente nunca dispara.
export const SINAIS_DE_DESLIGAMENTO = ['SIGINT', 'SIGTERM', 'SIGHUP', 'SIGBREAK'];
