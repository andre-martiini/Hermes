// Executa `tarefa` uma vez por vez. Pedidos que chegam durante uma execução viram
// UMA nova execução ao final — nem descartados (a mensagem nova esperaria o cron
// do minuto seguinte), nem empilhados (uma rajada de 50 avisos não vira 50 rodadas).

export function criarExecutorCoalescido(tarefa) {
    let rodando = false;
    let repetir = false;

    return async function solicitar() {
        if (rodando) {
            repetir = true;
            return;
        }
        rodando = true;
        try {
            do {
                repetir = false;
                await tarefa();
            } while (repetir);
        } finally {
            rodando = false;
        }
    };
}
