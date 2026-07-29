import { FinanceSettings, FinanceTransaction } from '../../types';

export const parseFinanceTransactionDate = (dateStr?: string) => {
  if (!dateStr) return null;

  const isoMatch = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (isoMatch) {
    return {
      year: Number(isoMatch[1]),
      month: Number(isoMatch[2]) - 1,
      day: Number(isoMatch[3])
    };
  }

  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return null;

  return {
    year: date.getFullYear(),
    month: date.getMonth(),
    day: date.getDate()
  };
};

export const isPixFinanceTransaction = (transaction: FinanceTransaction) => {
  const category = transaction.category?.toLocaleLowerCase('pt-BR') || '';
  const description = transaction.description?.toLocaleLowerCase('pt-BR') || '';
  return category.includes('pix') || description.includes('pix');
};

export const getMonthlyBudget = (
  settings: FinanceSettings,
  year: number,
  month: number
) => {
  const periodKey = `${year}-${String(month + 1).padStart(2, '0')}`;
  return settings.monthlyBudgets?.[periodKey] || settings.monthlyBudget || 0;
};

export const getFinancePeriodSummary = (
  transactions: FinanceTransaction[],
  settings: FinanceSettings,
  year: number,
  month: number
) => {
  const periodTransactions = transactions.filter(transaction => {
    if (transaction.status === 'deleted') return false;
    const date = parseFinanceTransactionDate(transaction.date);
    return date?.year === year && date.month === month;
  });
  const budget = getMonthlyBudget(settings, year, month);
  const totalSpend = periodTransactions.reduce((sum, transaction) => sum + transaction.amount, 0);
  const pixSpend = periodTransactions
    .filter(isPixFinanceTransaction)
    .reduce((sum, transaction) => sum + transaction.amount, 0);

  return {
    budget,
    totalSpend,
    pixSpend,
    available: budget - totalSpend,
    pixAvailable: budget - pixSpend,
    budgetRatio: budget > 0 ? totalSpend / budget : 0
  };
};
