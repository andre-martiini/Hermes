import { describe, expect, it } from 'vitest';
import {
  flagsResultantes,
  getVisibleShoppingItems,
  linhaFlag,
  linhasImportaveis,
} from './shoppingTransitions';

const baseItems = [
  { id: 'a', isPurchased: false },
  { id: 'b', isPurchased: true },
  { id: 'c', isPurchased: true },
] as any;

describe('getVisibleShoppingItems', () => {
  it('keeps not purchased items visible', () => {
    const visible = getVisibleShoppingItems(baseItems, []);
    expect(visible.map((i: any) => i.id)).toEqual(['a']);
  });

  it('keeps exiting purchased items visible during transition', () => {
    const visible = getVisibleShoppingItems(baseItems, ['c']);
    expect(visible.map((i: any) => i.id)).toEqual(['a', 'c']);
  });
});

/**
 * `flagsResultantes` e `linhasImportaveis` sao espelhos de regras que vivem no
 * servidor (`functions/tools/lista_compras.py`). Os casos abaixo sao os mesmos
 * cobertos la em `functions/test_lista_compras.py` — e o que faz uma divergencia
 * futura quebrar um teste em vez de virar card mentindo na tela do usuario.
 */
describe('flagsResultantes', () => {
  const naoPlanejado = { isPlanned: false, isPurchased: false };
  const planejado = { isPlanned: true, isPurchased: false };
  const comprado = { isPlanned: true, isPurchased: true };

  it('em create, marcar comprado tambem planeja', () => {
    expect(flagsResultantes(naoPlanejado, false, true, true))
      .toEqual({ planejado: true, comprado: true });
  });

  it('em create, flag falsa nunca desmarca o que ja existe', () => {
    expect(flagsResultantes(comprado, false, false, true))
      .toEqual({ planejado: true, comprado: true });
  });

  it('em create sem pedido, o item existente fica como esta', () => {
    expect(flagsResultantes(planejado, undefined, undefined, true))
      .toEqual({ planejado: true, comprado: false });
  });

  it('em update, desplanejar tira o comprado junto', () => {
    expect(flagsResultantes(comprado, false, undefined, false))
      .toEqual({ planejado: false, comprado: false });
  });

  it('em update, marcar comprado planeja junto', () => {
    expect(flagsResultantes(naoPlanejado, undefined, true, false))
      .toEqual({ planejado: true, comprado: true });
  });

  it('em update, desmarcar a compra preserva o planejamento', () => {
    expect(flagsResultantes(comprado, undefined, false, false))
      .toEqual({ planejado: true, comprado: false });
  });
});

describe('linhaFlag', () => {
  it('mostra seta so onde ha transicao real', () => {
    expect(linhaFlag('Planejado', false, true, true)).toBe('Planejado: Nao -> Sim');
  });

  it('explica a regra quando criar nao desmarca', () => {
    expect(linhaFlag('Planejado', true, true, true)).toContain('nunca desmarca');
  });

  it('nao inventa transicao quando nada muda', () => {
    expect(linhaFlag('Comprado', false, false, false)).toBe('Comprado: Nao (segue igual)');
  });
});

describe('linhasImportaveis', () => {
  it('ignora linha em branco sem contar como descarte', () => {
    expect(linhasImportaveis('queijo\n\n   \nmanteiga'))
      .toEqual({ nomes: ['queijo', 'manteiga'], descartadas: 0 });
  });

  it('descarta nome repetido no proprio texto, ignorando acento e caixa', () => {
    expect(linhasImportaveis('Pó de Café\npo de cafe'))
      .toEqual({ nomes: ['Pó de Café'], descartadas: 1 });
  });

  it('descarta linha sem nome antes da barra', () => {
    expect(linhasImportaveis('|Frios\nqueijo'))
      .toEqual({ nomes: ['queijo'], descartadas: 1 });
  });

  it('usa so a parte antes da barra como nome', () => {
    expect(linhasImportaveis('muçarela|Frios').nomes).toEqual(['muçarela']);
  });
});
