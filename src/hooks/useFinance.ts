import { useState, useEffect } from 'react';
import { collection, onSnapshot, doc, updateDoc, addDoc, deleteDoc, query } from 'firebase/firestore';
import { db } from '../firebase';
import {
  FinanceTransaction, FinanceGoal, FinanceSettings, FixedBill, BillRubric,
  IncomeEntry, IncomeRubric, Tarefa
} from '../types';
import { formatDateLocalISO } from '../types';
import { normalizeStatus } from '../utils/helpers';

export const useFinance = (
  tarefas: Tarefa[],
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void
) => {
  const [financeTransactions, setFinanceTransactions] = useState<FinanceTransaction[]>([]);
  const [financeGoals, setFinanceGoals] = useState<FinanceGoal[]>([]);
  const [financeSettings, setFinanceSettings] = useState<FinanceSettings>({
    monthlyBudget: 5000,
    monthlyBudgets: {},
    sprintDates: { 1: "08", 2: "15", 3: "22", 4: "01" },
    emergencyReserveTarget: 0,
    emergencyReserveCurrent: 0,
    billCategories: ['Conta Fixa', 'Poupança', 'Investimento'],
    incomeCategories: ['Renda Principal', 'Renda Extra', 'Dividendos', 'Outros']
  });
  const [fixedBills, setFixedBills] = useState<FixedBill[]>([]);
  const [billRubrics, setBillRubrics] = useState<BillRubric[]>([]);
  const [incomeEntries, setIncomeEntries] = useState<IncomeEntry[]>([]);
  const [incomeRubrics, setIncomeRubrics] = useState<IncomeRubric[]>([]);

  const [activeTab, setActiveTab] = useState<'dashboard' | 'fixed'>('dashboard');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  useEffect(() => {
    const unsubTransactions = onSnapshot(collection(db, 'finance_transactions'), (snapshot) => {
      setFinanceTransactions(snapshot.docs
        .map(d => ({ id: d.id, ...d.data() } as FinanceTransaction))
        .filter(t => t.status !== 'deleted')
      );
    });
    const unsubGoals = onSnapshot(collection(db, 'finance_goals'), (snapshot) => {
      setFinanceGoals(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as FinanceGoal)));
    });
    const unsubSettings = onSnapshot(doc(db, 'finance_settings', 'config'), (doc) => {
      if (doc.exists()) {
        setFinanceSettings(doc.data() as FinanceSettings);
      }
    });

    const qFixedBills = query(collection(db, 'fixed_bills'));
    const unsubFixedBills = onSnapshot(qFixedBills, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as FixedBill));
      setFixedBills(data);
    });

    const unsubRubrics = onSnapshot(collection(db, 'bill_rubrics'), (snapshot) => {
      setBillRubrics(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as BillRubric)));
    });

    const unsubIncomeEntries = onSnapshot(collection(db, 'income_entries'), (snapshot) => {
      setIncomeEntries(snapshot.docs
        .map(d => ({ id: d.id, ...d.data() } as IncomeEntry))
        .filter(e => e.status !== 'deleted')
      );
    });

    const unsubIncomeRubrics = onSnapshot(collection(db, 'income_rubrics'), (snapshot) => {
      setIncomeRubrics(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as IncomeRubric)));
    });

    return () => {
      unsubTransactions();
      unsubGoals();
      unsubSettings();
      unsubFixedBills();
      unsubRubrics();
      unsubIncomeEntries();
      unsubIncomeRubrics();
    };
  }, []);

  // Finance Processing Logic (Automatic from Tasks)
  useEffect(() => {
    const processFinanceTasks = async () => {
      const financeTasks = tarefas.filter(t =>
        t.status !== 'excluído' as any &&
        t.titulo.toLowerCase().includes('gasto semanal') &&
        t.notas && /Tag:\s*GASTO\s*SEMANAL/i.test(t.notas)
      );

      for (const task of financeTasks) {
        const valueMatch = task.notas?.match(/Valor:\s*R\$\s*([\d\.,]+)/i);
        if (valueMatch) {
          try {
            const amountStr = valueMatch[1].replace(/\./g, '').replace(',', '.');
            const amount = parseFloat(amountStr);

            if (isNaN(amount)) continue;

            const dateMatch = task.titulo.match(/(\d{2}\/\d{2}\/\d{4})/);
            let transactionDate = new Date().toISOString();
            if (dateMatch) {
              const [d, m, y] = dateMatch[1].split('/').map(Number);
              transactionDate = new Date(y, m - 1, d).toISOString();
            }

            const day = new Date(transactionDate).getDate();
            const sprintOriginal = day < 8 ? 1 : day < 15 ? 2 : day < 22 ? 3 : 4;

            const existingTransaction = financeTransactions.find(ft =>
              ft.originalTaskId === task.id ||
              (ft.category === 'Gasto Semanal' && ft.description.toLowerCase() === task.titulo.toLowerCase())
            );

            if (existingTransaction) {
              const hasChanged = existingTransaction.amount !== amount ||
                existingTransaction.date !== transactionDate ||
                existingTransaction.originalTaskId !== task.id;

              if (hasChanged) {
                await updateDoc(doc(db, 'finance_transactions', existingTransaction.id), {
                  amount,
                  date: transactionDate,
                  sprint: sprintOriginal,
                  description: task.titulo,
                  originalTaskId: task.id
                });

                if (existingTransaction.amount !== amount) {
                  showToast(`Valor atualizado: R$ ${amount.toLocaleString('pt-BR')}`, 'info');
                }
              }
            } else {
              await addDoc(collection(db, 'finance_transactions'), {
                description: task.titulo,
                amount,
                date: transactionDate,
                sprint: sprintOriginal,
                category: 'Gasto Semanal',
                originalTaskId: task.id
              });

              if (normalizeStatus(task.status) !== 'concluido') {
                await updateDoc(doc(db, 'tarefas', task.id), {
                  status: 'concluído',
                  data_conclusao: formatDateLocalISO(new Date())
                });
                showToast(`Gasto processado: R$ ${amount.toLocaleString('pt-BR')}`, 'success');
              }
            }
          } catch (error) {
            console.error("Erro ao processar tarefa financeira:", error);
          }
        }
      }
    };

    if (tarefas.length > 0) {
      processFinanceTasks();
    }
  }, [tarefas, financeTransactions, showToast]);

  // Handlers
  const handleUpdateFinanceGoal = async (id: string, updates: Partial<FinanceGoal>) => {
    try {
      await updateDoc(doc(db, 'finance_goals', id), updates);
      if (updates.currentAmount !== undefined || updates.targetAmount !== undefined) {
        // showToast("Meta atualizada!", "success"); // Optional feedback
      }
    } catch (e) {
      console.error(e);
      showToast("Erro ao atualizar meta.", "error");
    }
  };

  const handleDeleteFinanceGoal = async (id: string) => {
    if (!window.confirm("Excluir esta meta?")) return;
    try {
      await deleteDoc(doc(db, 'finance_goals', id));
      showToast("Meta removida.", "info");
    } catch (e) {
      showToast("Erro ao remover meta.", "error");
    }
  };

  const handleReorderFinanceGoals = async (startIndex: number, endIndex: number) => {
    const reordered = [...financeGoals];
    const [removed] = reordered.splice(startIndex, 1);
    reordered.splice(endIndex, 0, removed);

    // Optimistic update
    setFinanceGoals(reordered);

    // Batch update priorities
    try {
      const promises = reordered.map((g, index) =>
        updateDoc(doc(db, 'finance_goals', g.id), { priority: index + 1 })
      );
      await Promise.all(promises);
    } catch (e) {
      console.error(e);
      showToast("Erro ao reordenar metas.", "error");
    }
  };

  return {
    financeTransactions,
    financeGoals,
    financeSettings,
    fixedBills,
    billRubrics,
    incomeEntries,
    incomeRubrics,
    activeTab,
    setActiveTab,
    isSettingsOpen,
    setIsSettingsOpen,
    handleUpdateFinanceGoal,
    handleDeleteFinanceGoal,
    handleReorderFinanceGoals
  };
};
