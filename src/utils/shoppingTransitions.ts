import { ShoppingItem } from '@/types';

export const getVisibleShoppingItems = (plannedItems: ShoppingItem[], exitingPurchasedIds: string[]) =>
  plannedItems.filter((item) => !item.isPurchased || exitingPurchasedIds.includes(item.id));
