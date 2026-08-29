import { ShoppingItem } from '@/types';

export const getVisibleShoppingItems = (plannedItems: ShoppingItem[], exitingPurchasedIds: string[]) =>
  plannedItems.filter((item) => !item.isPurchased || exitingPurchasedIds.includes(item.id));

export const normalizeShoppingText = (value?: string | null) =>
  (value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();

/**
 * Espelho da regra de flags do servidor (`_resolver_flags` em
 * `functions/tools/lista_compras.py`): comprado implica planejado, e desplanejar
 * tira o comprado.
 *
 * O card de confirmacao precisa da MESMA regra porque so mostra a verdade quem
 * calcula o estado final — prever flag por flag faz o card prometer transicoes
 * que o servidor refaz. Como e um espelho, ele mora aqui, sob teste: e a unica
 * forma de a divergencia com o servidor quebrar um teste em vez de aparecer na
 * tela do usuario.
 *
 * `aditivo` e o modo de `create` sobre item que ja existe: flag falsa e
 * descartada, entao o pedido so acrescenta.
 */
export const flagsResultantes = (
  atual: { isPlanned: boolean; isPurchased: boolean },
  pedidoPlanejado: boolean | undefined,
  pedidoComprado: boolean | undefined,
  aditivo: boolean,
) => {
  if (aditivo) {
    const comprado = atual.isPurchased || pedidoComprado === true;
    return { planejado: atual.isPlanned || pedidoPlanejado === true || comprado, comprado };
  }
  let planejado = pedidoPlanejado !== undefined ? pedidoPlanejado : atual.isPlanned;
  let comprado = pedidoComprado !== undefined ? pedidoComprado : atual.isPurchased;
  if (comprado && !planejado) {
    if (pedidoPlanejado !== undefined && pedidoComprado === undefined) comprado = false;
    else planejado = true;
  }
  if (!planejado) comprado = false;
  return { planejado, comprado };
};

export const linhaFlag = (rotulo: string, atual: boolean, final: boolean, aditivo: boolean) => {
  if (atual !== final) return `${rotulo}: ${atual ? 'Sim' : 'Nao'} -> ${final ? 'Sim' : 'Nao'}`;
  if (atual && aditivo) return `${rotulo}: Sim (segue igual — "criar" nunca desmarca)`;
  return `${rotulo}: ${atual ? 'Sim' : 'Nao'} (segue igual)`;
};

/**
 * Espelho de `_parse_linhas` + a deduplicacao de `importar_lote`: linha vazia
 * some, nome vazio e nome repetido dentro do proprio texto sao descartados.
 *
 * Contar linha crua faria o card prometer mais itens do que a importacao cria.
 * Como o resultado da callable e descartado e a UI so mostra um toast generico,
 * este card e a unica previsao que o usuario ve antes de confirmar.
 */
export const linhasImportaveis = (rawText: string) => {
  const vistos = new Set<string>();
  const nomes: string[] = [];
  let descartadas = 0;
  (rawText || '').split('\n').forEach((linha) => {
    const limpa = linha.trim();
    if (!limpa) return;
    const nome = (limpa.includes('|') ? limpa.split('|')[0] : limpa).trim();
    const chave = normalizeShoppingText(nome);
    if (!nome || vistos.has(chave)) {
      descartadas += 1;
      return;
    }
    vistos.add(chave);
    nomes.push(nome);
  });
  return { nomes, descartadas };
};
