/**
 * Pausa dos ouvintes do Firestore quando ninguém está olhando.
 *
 * Por quê: em 30–31/10/2026 um aparelho esquecido com o Gaspar aberto (tablet) chegou a 3–5 milhões
 * de leituras por dia. Cada ouvinte aberto é uma leitura por documento a cada reconexão; sem ninguém
 * olhando, é gasto puro. A pausa cancela todos os ouvintes e, quando a pessoa volta, assina de novo
 * (o Firestore entrega o estado atual em segundos; com o cache local, a maior parte vem de graça).
 *
 * `GerenciadorOuvintes` guarda como assinar cada ouvinte; `ativarPausaOciosa` decide quando pausar.
 */

type Cancelar = () => void;

interface Item {
    inscrever: () => Cancelar;
    cancela: Cancelar | null;
}

export class GerenciadorOuvintes {
    private itens = new Set<Item>();
    private motivos = new Set<string>();

    /** Pausado por qualquer motivo (ociosidade, outra sessão ativa...). */
    get pausado(): boolean {
        return this.motivos.size > 0;
    }

    /** Assina agora (ou ao retomar, se estiver pausado). Devolve o cancelamento definitivo. */
    registrar(inscrever: () => Cancelar): Cancelar {
        const item: Item = { inscrever, cancela: null };
        this.itens.add(item);
        if (!this.pausado) {
            try {
                item.cancela = inscrever();
            } catch (erro) {
                this.itens.delete(item);
                throw erro;
            }
        }
        return () => {
            this.itens.delete(item);
            item.cancela?.();
            item.cancela = null;
        };
    }

    pausar(motivo = 'ocio'): void {
        const jaPausado = this.pausado;
        this.motivos.add(motivo);
        if (jaPausado) return;
        for (const item of this.itens) {
            item.cancela?.();
            item.cancela = null;
        }
    }

    /** Só volta a assinar quando nenhum motivo de pausa restar. */
    retomar(motivo = 'ocio'): void {
        if (!this.motivos.delete(motivo) || this.pausado) return;
        for (const item of [...this.itens]) {
            if (!this.itens.has(item) || item.cancela) continue;
            try {
                item.cancela = item.inscrever();
            } catch (erro) {
                // Um ouvinte inválido não pode impedir os outros de voltar.
                this.itens.delete(item);
                console.error('[ouvintes] falha ao reassinar:', erro);
            }
        }
    }
}

export const OCULTA_MS = 10 * 60_000;
export const SEM_ATIVIDADE_MS = 60 * 60_000;
const VERIFICA_A_CADA_MS = 60_000;
const EVENTOS_DE_ATIVIDADE = ['pointerdown', 'keydown', 'wheel', 'touchstart', 'mousemove'] as const;

/**
 * Pausa quando a aba fica escondida por `ocultaMs` ou quando fica visível sem nenhum toque, tecla
 * ou movimento por `semAtividadeMs`; retoma na hora em que a aba reaparece ou há qualquer atividade.
 * Devolve a função que desliga tudo (usada nos testes).
 */
export function ativarPausaOciosa(
    g: GerenciadorOuvintes,
    doc: Document,
    opcoes: { ocultaMs?: number; semAtividadeMs?: number; agora?: () => number } = {},
): () => void {
    const ocultaMs = opcoes.ocultaMs ?? OCULTA_MS;
    const semAtividadeMs = opcoes.semAtividadeMs ?? SEM_ATIVIDADE_MS;
    const agora = opcoes.agora ?? Date.now;
    let ultimaAtividade = agora();
    let timerOculta: ReturnType<typeof setTimeout> | null = null;

    const limparOculta = () => {
        if (timerOculta) clearTimeout(timerOculta);
        timerOculta = null;
    };
    const voltou = () => {
        ultimaAtividade = agora();
        limparOculta();
        g.retomar();
    };
    const aoMudarVisibilidade = () => {
        if (doc.visibilityState === 'hidden') {
            limparOculta();
            timerOculta = setTimeout(() => g.pausar(), ocultaMs);
        } else {
            voltou();
        }
    };
    const aoHaverAtividade = () => {
        ultimaAtividade = agora();
        if (g.pausado) g.retomar();
    };
    const verificar = setInterval(() => {
        if (doc.visibilityState !== 'hidden' && agora() - ultimaAtividade >= semAtividadeMs) g.pausar();
    }, VERIFICA_A_CADA_MS);

    doc.addEventListener('visibilitychange', aoMudarVisibilidade);
    for (const e of EVENTOS_DE_ATIVIDADE) doc.addEventListener(e, aoHaverAtividade, { passive: true, capture: true });
    // Se a página já abre escondida (aba restaurada em segundo plano), o relógio da pausa começa agora.
    if (doc.visibilityState === 'hidden') aoMudarVisibilidade();

    return () => {
        clearInterval(verificar);
        limparOculta();
        doc.removeEventListener('visibilitychange', aoMudarVisibilidade);
        for (const e of EVENTOS_DE_ATIVIDADE) doc.removeEventListener(e, aoHaverAtividade, { capture: true });
    };
}
