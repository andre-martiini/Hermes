import { describe, expect, it } from 'vitest';
import { resolveTwoStepAction } from './destructiveActions';

describe('resolveTwoStepAction', () => {
  it('should enter confirmation mode on first click', () => {
    const result = resolveTwoStepAction(null, 'item_1');
    expect(result).toEqual({ pendingKey: 'item_1', confirmed: false });
  });

  it('should confirm on second click for the same key', () => {
    const result = resolveTwoStepAction('item_1', 'item_1');
    expect(result).toEqual({ pendingKey: null, confirmed: true });
  });

  it('should switch pending key when user clicks another target', () => {
    const result = resolveTwoStepAction('item_1', 'item_2');
    expect(result).toEqual({ pendingKey: 'item_2', confirmed: false });
  });
});
