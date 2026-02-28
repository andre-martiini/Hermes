import { describe, expect, it } from 'vitest';
import { getVisibleShoppingItems } from './shoppingTransitions';

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
