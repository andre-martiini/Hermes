import { useState, useEffect } from 'react';
import { collection, doc, addDoc, updateDoc, deleteDoc, onSnapshot, setDoc } from 'firebase/firestore';
import { db } from '../firebase';
import { Tarefa, FinanceTransaction, FinanceGoal, FinanceSettings, FixedBill, BillRubric, IncomeEntry, IncomeRubric, formatDateLocalISO } from '../types';
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
  const [loading, setLoading] = useState(true);

  // Sync Finance Data
  useEffect(() => {
    setLoading(true);
    const unsubTransactions = onSnapshot(collection(db, 'finance_transactions'), (snapshot) => {
      setFinanceTransactions(snapshot.docs
        .map(d => ({ id: d.id, ...d.data() } as FinanceTransaction))
        .filter(t => t.status !== 'deleted')
      );
    });

    const unsubGoals = onSnapshot(collection(db, 'finance_goals'), (snapshot) => {
      setFinanceGoals(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as FinanceGoal)));
    });

    const unsubSettings = onSnapshot(doc(db, 'finance_settings', 'config'), (docSnap) => {
      if (docSnap.exists()) {
        setFinanceSettings(docSnap.data() as FinanceSettings);
      }
    });

    const unsubFixedBills = onSnapshot(collection(db, 'fixed_bills'), (snapshot) => {
       setFixedBills(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as FixedBill)));
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
      setLoading(false);
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

  // Automatic Processing of Finance Tasks
  useEffect(() => {
    const processFinanceTasks = async () => {
      const financeTasks = tarefas.filter(t =>
        (t.status as any) !== 'excluído' &&
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
                originalTaskId: task.id,
                status: 'active'
              });

              if (normalizeStatus(task.status) !== 'concluido') {
                await updateDoc(doc(db, 'tarefas', task.id), {
                  status: 'concluído',
                  data_conclusao: formatDateLocalISO(new Date()),
                  data_atualizacao: new Date().toISOString()
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
  const handleUpdateFinanceGoal = async (goal: FinanceGoal) => {
    try {
      await updateDoc(doc(db, 'finance_goals', goal.id), goal as any);
      showToast("Meta atualizada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar meta.", "error");
    }
  };

  const handleDeleteFinanceGoal = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'finance_goals', id));
      showToast("Meta removida!", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover meta.", "error");
    }
  };

  const handleReorderFinanceGoals = async (reorderedGoals: FinanceGoal[]) => {
    try {
      const promises = reorderedGoals.map((goal, index) =>
        updateDoc(doc(db, 'finance_goals', goal.id), { priority: index + 1 })
      );
      await Promise.all(promises);
      showToast("Prioridades atualizadas!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao reordenar metas.", "error");
    }
  };

  const handleAddTransaction = async (t: Partial<FinanceTransaction>) => {
     await addDoc(collection(db, 'finance_transactions'), { ...t, status: 'active' });
     showToast("Transação adicionada.", "success");
  };

  const handleUpdateTransaction = async (t: FinanceTransaction) => {
     await updateDoc(doc(db, 'finance_transactions', t.id), t as any);
     showToast("Transação atualizada.", "success");
  };

  const handleDeleteTransaction = async (id: string) => {
     await updateDoc(doc(db, 'finance_transactions', id), { status: 'deleted' });
     showToast("Transação removida.", "info");
  };

  // Settings
  const handleUpdateSettings = async (newSettings: FinanceSettings) => {
     await setDoc(doc(db, 'finance_settings', 'config'), newSettings);
     showToast("Configurações financeiras salvas.", "success");
  };

  // Rubrics & Bills
  const handleAddRubric = async (rubric: Partial<BillRubric>) => { await addDoc(collection(db, 'bill_rubrics'), rubric); };
  const handleUpdateRubric = async (rubric: BillRubric) => { await updateDoc(doc(db, 'bill_rubrics', rubric.id), rubric as any); };
  const handleDeleteRubric = async (id: string) => { await deleteDoc(doc(db, 'bill_rubrics', id)); };

  const handleAddBill = async (bill: Partial<FixedBill>) => { await addDoc(collection(db, 'fixed_bills'), bill); };
  const handleUpdateBill = async (bill: FixedBill) => { await updateDoc(doc(db, 'fixed_bills', bill.id), bill as any); };
  const handleDeleteBill = async (id: string) => { await deleteDoc(doc(db, 'fixed_bills', id)); };

  const handleAddIncomeRubric = async (rubric: Partial<IncomeRubric>) => { await addDoc(collection(db, 'income_rubrics'), rubric); };
  const handleUpdateIncomeRubric = async (rubric: IncomeRubric) => { await updateDoc(doc(db, 'income_rubrics', rubric.id), rubric as any); };
  const handleDeleteIncomeRubric = async (id: string) => { await deleteDoc(doc(db, 'income_rubrics', id)); };

  const handleAddIncomeEntry = async (entry: Partial<IncomeEntry>) => { await addDoc(collection(db, 'income_entries'), { ...entry, status: 'active' }); };
  const handleUpdateIncomeEntry = async (entry: IncomeEntry) => { await updateDoc(doc(db, 'income_entries', entry.id), entry as any); };
  const handleDeleteIncomeEntry = async (id: string) => { await updateDoc(doc(db, 'income_entries', id), { status: 'deleted' }); };

  return {
    financeTransactions,
    financeGoals,
    financeSettings,
    fixedBills,
    billRubrics,
    incomeEntries,
    incomeRubrics,
    loading,
    handleUpdateFinanceGoal,
    handleDeleteFinanceGoal,
    handleReorderFinanceGoals,
    handleAddTransaction,
    handleUpdateTransaction,
    handleDeleteTransaction,
    handleUpdateSettings,
    handleAddRubric,
    handleUpdateRubric,
    handleDeleteRubric,
    handleAddBill,
    handleUpdateBill,
    handleDeleteBill,
    handleAddIncomeRubric,
    handleUpdateIncomeRubric,
    handleDeleteIncomeRubric,
    handleAddIncomeEntry,
    handleUpdateIncomeEntry,
    handleDeleteIncomeEntry
  };
};
