import { describe, expect, it } from 'vitest';
import { FinanceSettings, FinanceTransaction } from '../../types';
import {
  getFinancePeriodSummary,
  isPixFinanceTransaction,
  parseFinanceTransactionDate
} from './financeBudget';

const settings: FinanceSettings = {
  monthlyBudget: 5000,
  monthlyBudgets: { '2026-07': 6000 },
  sprintDates: {},
  emergencyReserveTarget: 0,
  emergencyReserveCurrent: 0,
  billCategories: [],
  incomeCategories: []
};

const transaction = (
  id: string,
  amount: number,
  date: string,
  description = 'Compra',
  category = 'Geral',
  status: FinanceTransaction['status'] = 'active'
): FinanceTransaction => ({
  id,
  amount,
  date,
  description,
  category,
  status,
  sprint: 1
});

describe('financeBudget', () => {
  it('uses the calendar date encoded in ISO strings without timezone drift', () => {
    expect(parseFinanceTransactionDate('2026-07-01T00:30:00.000Z')).toEqual({
      year: 2026,
      month: 6,
      day: 1
    });
  });

  it('calculates the general and Pix balances from active period transactions', () => {
    const result = getFinancePeriodSummary([
      transaction('pix-description', 100, '2026-07-01T10:00:00Z', 'Pix realizado'),
      transaction('pix-category', 50, '2026-07-02T10:00:00Z', 'Transferência', 'Pix'),
      transaction('other', 25, '2026-07-03T10:00:00Z'),
      transaction('deleted', 500, '2026-07-04T10:00:00Z', 'Pix realizado', 'Pix', 'deleted'),
      transaction('other-month', 1000, '2026-08-01T00:00:00Z')
    ], settings, 2026, 6);

    expect(result).toMatchObject({
      budget: 6000,
      totalSpend: 175,
      pixSpend: 150,
      available: 5825,
      pixAvailable: 5850
    });
    expect(result.budgetRatio).toBeCloseTo(175 / 6000);
  });

  it('recognizes Pix from either category or description', () => {
    expect(isPixFinanceTransaction(transaction('1', 10, '2026-07-01', 'PIX enviado'))).toBe(true);
    expect(isPixFinanceTransaction(transaction('2', 10, '2026-07-01', 'Transferência', 'Pix'))).toBe(true);
    expect(isPixFinanceTransaction(transaction('3', 10, '2026-07-01'))).toBe(false);
  });
});
