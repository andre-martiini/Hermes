import { useState, useEffect } from 'react';
import { collection, doc, onSnapshot, query } from 'firebase/firestore';
import type { Firestore } from 'firebase/firestore';
import type { User } from 'firebase/auth';
import type {
  FinanceTransaction,
  FinanceGoal,
  FinanceSettings,
  FixedBill,
  BillRubric,
  IncomeEntry,
  IncomeRubric,
  ShoppingItem,
  Servico,
} from '../../types';
import { orderBy } from 'firebase/firestore';

const DEFAULT_FINANCE_SETTINGS: FinanceSettings = {
  monthlyBudget: 5000,
  monthlyBudgets: {},
  sprintDates: { 1: "08", 2: "15", 3: "22", 4: "01" },
  emergencyReserveTarget: 0,
  emergencyReserveCurrent: 0,
  billCategories: ['Conta Fixa', 'Poupança', 'Investimento'],
  incomeCategories: ['Renda Principal', 'Renda Extra', 'Dividendos', 'Outros'],
};

export interface FinanceData {
  financeTransactions: FinanceTransaction[];
  financeGoals: FinanceGoal[];
  financeSettings: FinanceSettings;
  fixedBills: FixedBill[];
  billRubrics: BillRubric[];
  incomeEntries: IncomeEntry[];
  incomeRubrics: IncomeRubric[];
  shoppingItems: ShoppingItem[];
  services: Servico[];
}

export function useFinanceData(db: Firestore, user: User | null): FinanceData {
  const [financeTransactions, setFinanceTransactions] = useState<FinanceTransaction[]>([]);
  const [financeGoals, setFinanceGoals] = useState<FinanceGoal[]>([]);
  const [financeSettings, setFinanceSettings] = useState<FinanceSettings>(DEFAULT_FINANCE_SETTINGS);
  const [fixedBills, setFixedBills] = useState<FixedBill[]>([]);
  const [billRubrics, setBillRubrics] = useState<BillRubric[]>([]);
  const [incomeEntries, setIncomeEntries] = useState<IncomeEntry[]>([]);
  const [incomeRubrics, setIncomeRubrics] = useState<IncomeRubric[]>([]);
  const [shoppingItems, setShoppingItems] = useState<ShoppingItem[]>([]);
  const [services, setServices] = useState<Servico[]>([]);

  useEffect(() => {
    if (!user) return;

    const unsubTransactions = onSnapshot(collection(db, 'finance_transactions'), (snapshot) => {
      setFinanceTransactions(
        snapshot.docs
          .map(d => ({ id: d.id, ...d.data() } as FinanceTransaction))
          .filter(t => t.status !== 'deleted'),
      );
    });

    const unsubGoals = onSnapshot(collection(db, 'finance_goals'), (snapshot) => {
      setFinanceGoals(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as FinanceGoal)));
    });

    const unsubSettings = onSnapshot(doc(db, 'finance_settings', 'config'), (docSnap) => {
      if (docSnap.exists()) setFinanceSettings(docSnap.data() as FinanceSettings);
    });

    const unsubFixedBills = onSnapshot(query(collection(db, 'fixed_bills')), (snapshot) => {
      setFixedBills(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as FixedBill)));
    });

    const unsubRubrics = onSnapshot(collection(db, 'bill_rubrics'), (snapshot) => {
      setBillRubrics(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as BillRubric)));
    });

    const unsubIncomeEntries = onSnapshot(collection(db, 'income_entries'), (snapshot) => {
      setIncomeEntries(
        snapshot.docs
          .map(d => ({ id: d.id, ...d.data() } as IncomeEntry))
          .filter(e => e.status !== 'deleted'),
      );
    });

    const unsubIncomeRubrics = onSnapshot(collection(db, 'income_rubrics'), (snapshot) => {
      setIncomeRubrics(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as IncomeRubric)));
    });

    const unsubShopping = onSnapshot(collection(db, 'shopping_items'), (snapshot) => {
      setShoppingItems(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as ShoppingItem)));
    });

    const qServices = query(collection(db, 'servicos'), orderBy('data_criacao', 'desc'));
    const unsubServices = onSnapshot(qServices, (snapshot) => {
      setServices(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as Servico)));
    });

    return () => {
      unsubTransactions();
      unsubGoals();
      unsubSettings();
      unsubFixedBills();
      unsubRubrics();
      unsubIncomeEntries();
      unsubIncomeRubrics();
      unsubShopping();
      unsubServices();
    };
  }, [db, user]);

  return {
    financeTransactions,
    financeGoals,
    financeSettings,
    fixedBills,
    billRubrics,
    incomeEntries,
    incomeRubrics,
    shoppingItems,
    services,
  };
}
