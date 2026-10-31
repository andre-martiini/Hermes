/**
 * Sessão única: só um Gaspar aberto lê o Firestore por vez; o aberto mais recentemente vence.
 *
 * Quem abre (ou clica, toca, digita numa cópia que cedeu) grava seu id em `system/sessao_ativa`.
 * Todas as cópias escutam esse documento; a que vê outro id pausa seus ouvintes (motivo próprio no
 * GerenciadorOuvintes) e mostra um aviso. Mover o mouse não toma a sessão. Aba aberta escondida
 * (ex.: restaurada pelo Windows) só toma a sessão quando aparecer.
 */
import type { GerenciadorOuvintes } from './pausaOuvintes';

export const MOTIVO_OUTRA_SESSAO = 'outra-sessao';
const EVENTOS_DE_TOMADA = ['pointerdown', 'keydown', 'touchstart'] as const;

export interface DependenciasSessaoUnica {
    gerenciador: GerenciadorOuvintes;
    doc: Document;
    /** Id desta aba, novo a cada carga da página. */
    id: string;
    /** Escuta o documento de controle (sem passar pela pausa); entrega o id da sessão ativa. */
    escutar: (aoReceber: (idAtivo: string | null) => void) => () => void;
    /** Grava este id como a sessão ativa. */
    gravar: () => Promise<unknown>;
    aoMudar: (cedida: boolean) => void;
}

export function iniciarSessaoUnica(d: DependenciasSessaoUnica): () => void {
    let tomou = false;
    let cedida = false;
    // Entre pedir a tomada e ver o próprio id no documento, ids alheios são snapshots velhos.
    let aguardandoConfirmacao = false;

    const tomar = () => {
        tomou = true;
        aguardandoConfirmacao = true;
        if (cedida) {
            cedida = false;
            d.gerenciador.retomar(MOTIVO_OUTRA_SESSAO);
            d.aoMudar(false);
        }
        d.gravar().catch((erro) => console.warn('[sessao-unica] falha ao gravar sessão ativa:', erro));
    };

    const aoReceber = (idAtivo: string | null) => {
        if (!tomou || !idAtivo) return;
        if (idAtivo === d.id) {
            aguardandoConfirmacao = false;
            return;
        }
        if (aguardandoConfirmacao || cedida) return;
        cedida = true;
        d.gerenciador.pausar(MOTIVO_OUTRA_SESSAO);
        d.aoMudar(true);
    };

    const aoInteragir = () => {
        if (cedida) tomar();
    };
    const aoVisivel = () => {
        if (!tomou && d.doc.visibilityState !== 'hidden') tomar();
    };

    const parar = d.escutar(aoReceber);
    for (const e of EVENTOS_DE_TOMADA) d.doc.addEventListener(e, aoInteragir, { passive: true, capture: true });
    d.doc.addEventListener('visibilitychange', aoVisivel);
    aoVisivel();

    return () => {
        parar();
        for (const e of EVENTOS_DE_TOMADA) d.doc.removeEventListener(e, aoInteragir, { capture: true });
        d.doc.removeEventListener('visibilitychange', aoVisivel);
        if (cedida) {
            cedida = false;
            d.gerenciador.retomar(MOTIVO_OUTRA_SESSAO);
        }
    };
}
