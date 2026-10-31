/**
 * Entra no lugar de `firebase/firestore` em todo o app (alias em vite.config.ts): reexporta o pacote
 * real e troca só o `onSnapshot`, para que todo ouvinte passe pelo gerenciador que o pausa quando a
 * aba está escondida ou parada (ver pausaOuvintes.ts). Os 30+ arquivos continuam importando de
 * 'firebase/firestore' sem mudança.
 */
import * as real from '@firebase/firestore';
import { GerenciadorOuvintes, ativarPausaOciosa } from './pausaOuvintes';

export * from '@firebase/firestore';

const gerenciador = new GerenciadorOuvintes();
if (typeof document !== 'undefined') ativarPausaOciosa(gerenciador, document);

export function onSnapshot(...args: unknown[]): () => void {
    return gerenciador.registrar(() => (real.onSnapshot as (...a: unknown[]) => () => void)(...args));
}
