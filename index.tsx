
import React, { useState, useEffect, useMemo } from 'react';
import { createRoot } from 'react-dom/client';
import { Tarefa, Status, EntregaInstitucional, Prioridade, AtividadeRealizada, Afastamento } from './types';
import { STATUS_COLORS, PROJECT_COLORS } from './constants';
import { db } from './firebase';
import { collection, onSnapshot, query, updateDoc, doc, addDoc, deleteDoc } from 'firebase/firestore';


type SortOption = 'date-asc' | 'date-desc' | 'priority-high' | 'priority-low';
type DateFilter = 'today' | 'week' | 'month';

// --- Utilitários ---
const getDaysInMonth = (year: number, month: number) => new Date(year, month + 1, 0).getDate();

const isWorkDay = (date: Date) => {
  const day = date.getDay();
  return day !== 0 && day !== 6; // Seg-Sex
};

const getMonthWorkDays = (year: number, month: number) => {
  const days = [];
  const totalDays = getDaysInMonth(year, month);
  for (let d = 1; d <= totalDays; d++) {
    const date = new Date(year, month, d);
    if (isWorkDay(date)) days.push(new Date(date));
  }
  return days;
};

const normalizeStatus = (status: string): string => {
  if (!status) return 'pendente';
  return status
    .toLowerCase()
    .trim()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
};

const formatDate = (dateStr: string) => {
  if (!dateStr || dateStr === "-" || dateStr === "0000-00-00" || dateStr.trim() === "") return 'Sem Data';
  const parts = dateStr.split('-');
  if (parts.length !== 3) return dateStr;
  const [year, month, day] = parts.map(Number);
  const date = new Date(year, month - 1, day);
  if (isNaN(date.getTime())) return dateStr;
  const dayOfWeek = new Intl.DateTimeFormat('pt-BR', { weekday: 'long' }).format(date);
  const capitalizedDay = dayOfWeek.charAt(0).toUpperCase() + dayOfWeek.slice(1);
  return `${parts[2]}/${parts[1]}/${parts[0]} (${capitalizedDay})`;
};

// --- Subcomponentes Atômicos ---
const FilterChip = React.memo(({ label, isActive, onClick, colorClass }: { label: string, isActive: boolean, onClick: () => void, colorClass?: string }) => (
  <button
    onClick={onClick}
    className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest border-2 transition-all duration-200 active:scale-95 ${
      isActive 
        ? (colorClass || 'bg-slate-900 text-white border-slate-900 shadow-md') 
        : 'bg-white text-slate-400 border-slate-200 border-dashed hover:border-slate-400 hover:text-slate-600'
    }`}
  >
    {label}
  </button>
));

const PgcMiniTaskCard = React.memo(({ task, onClick }: { task: Tarefa, onClick: (t: Tarefa) => void }) => {
  return (
    <div 
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('tarefaId', task.id);
        e.dataTransfer.effectAllowed = 'link';
      }}
      onClick={() => onClick(task)}
      className="bg-white border border-slate-200 p-3 rounded-xl shadow-sm hover:shadow-md hover:border-blue-400 transition-all cursor-grab active:cursor-grabbing w-full md:w-[280px] group"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-[8px] font-black px-1.5 py-0.5 rounded uppercase ${PROJECT_COLORS[task.projeto] || 'bg-slate-100 text-slate-600'}`}>
          {task.projeto}
        </span>
        <span className="text-[8px] font-black text-slate-400 uppercase">{formatDate(task.data_limite)}</span>
      </div>
      <h5 className="text-[11px] font-bold text-slate-900 leading-tight group-hover:text-blue-600 line-clamp-2">{task.titulo}</h5>
    </div>
  );
});

const RowCard = React.memo(({ task, onClick }: { task: Tarefa, onClick: (t: Tarefa) => void }) => {
  const statusValue = task.status ? task.status.toLowerCase().trim() : 'pendente';
  const statusClass = STATUS_COLORS[statusValue] || STATUS_COLORS['default'];
  
  return (
    <div 
      onClick={() => onClick(task)} 
      className="group bg-white w-full p-8 border-b border-slate-200 hover:bg-slate-50 transition-all cursor-pointer flex flex-col md:flex-row md:items-center gap-6 md:gap-8 animate-in"
    >
      <div className="flex-1">
        <div className="flex items-center gap-3 mb-3">
          <span className={`text-[11px] font-black px-3 py-1 rounded-md uppercase tracking-widest bg-slate-100 border border-slate-200 ${PROJECT_COLORS[task.projeto] || 'text-slate-800'}`}>
            {task.projeto}
          </span>
          <div className={`text-[11px] font-black px-3 py-1 rounded-md border-2 uppercase tracking-widest ${statusClass}`}>
            {task.status || 'PENDENTE'}
          </div>
        </div>
        <h4 className="text-xl md:text-2xl font-black text-slate-900 tracking-tighter leading-none group-hover:text-blue-700 transition-colors">
          {task.titulo}
        </h4>
      </div>
      <div className="flex items-center justify-between md:justify-end gap-10 md:border-l md:border-slate-100 md:pl-10">
        <div className="text-left md:text-center min-w-[120px]">
          <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1.5">Prazo Final</p>
          <p className="text-lg font-black text-slate-900 tabular-nums">{formatDate(task.data_limite)}</p>
        </div>
        <div className="hidden md:flex bg-slate-900 text-white p-4 rounded-xl shadow-lg group-hover:bg-blue-600 transition-all items-center justify-center">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M9 5l7 7-7 7" /></svg>
        </div>
      </div>
    </div>
  );
});

const App: React.FC = () => {
  const [tarefas, setTarefas] = useState<Tarefa[]>([]);
  const [entregas, setEntregas] = useState<EntregaInstitucional[]>([]);
  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [viewMode, setViewMode] = useState<'gallery' | 'pgc'>('gallery');
  const [selectedTask, setSelectedTask] = useState<Tarefa | null>(null);
  const [lastSync, setLastSync] = useState<Date | null>(null);
  const [isPanelExpanded, setIsPanelExpanded] = useState(false);

  const [statusFilter, setStatusFilter] = useState<Status[]>(['pendente', 'em andamento']);
  const [sortOption, setSortOption] = useState<SortOption>('date-asc');
  const [expandedSections, setExpandedSections] = useState<string[]>([]);
  const [hasAutoExpanded, setHasAutoExpanded] = useState(false);
  const [newNote, setNewNote] = useState('');

  // Estados PGC
  const [atividadesPGC, setAtividadesPGC] = useState<AtividadeRealizada[]>([]);
  const [afastamentos, setAfastamentos] = useState<Afastamento[]>([]);
  const [pgcSubView, setPgcSubView] = useState<'audit' | 'heatmap' | 'config'>('audit');
  const [isBatchImportOpen, setIsBatchImportOpen] = useState(false);
  const [isAddActivityOpen, setIsAddActivityOpen] = useState(false);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [unidades, setUnidades] = useState<{id: string, nome: string}[]>([]);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [newUnidade, setNewUnidade] = useState('');
  const [isAddTaskOpen, setIsAddTaskOpen] = useState(false);

  const handleUpdateTarefa = async (id: string, updates: Partial<Tarefa>) => {
    try {
      const docRef = doc(db, 'tarefas', id);
      await updateDoc(docRef, {
        ...updates,
        data_atualizacao: new Date().toISOString()
      });
    } catch (err) {
      console.error("Erro ao atualizar tarefa:", err);
      setError("Erro ao salvar alterações.");
    }
  };

  const handleCreateTarefa = async (tarefa: Omit<Tarefa, 'id'>) => {
    try {
      const col = collection(db, 'tarefas');
      await addDoc(col, {
        ...tarefa,
        data_criacao: new Date().toISOString(),
        data_atualizacao: new Date().toISOString(),
        acompanhamento: []
      });
      setIsAddTaskOpen(false);
    } catch (err) {
      console.error(err);
      setError("Erro ao criar tarefa.");
    }
  };

  const handleAddHistory = async (task: Tarefa) => {
    if (!newNote.trim()) return;
    const newLog = {
      data: new Date().toISOString().split('T')[0],
      nota: newNote.trim()
    };
    const updatedAcompanhamento = [newLog, ...(task.acompanhamento || [])];
    await handleUpdateTarefa(task.id, { acompanhamento: updatedAcompanhamento });
    setNewNote('');
  };

  const handleSaveAtividade = async (atividade: Omit<AtividadeRealizada, 'id'>) => {
    try {
      const col = collection(db, 'atividades_pgc');
      await addDoc(col, atividade);
      setIsAddActivityOpen(false);
    } catch (err) {
      console.error(err);
      setError("Erro ao salvar atividade.");
    }
  };

  const handleAddEntrega = async (entrega: string, area: string, descricao_trabalho?: string) => {
    try {
      await addDoc(collection(db, 'atividades'), {
        entrega,
        area,
        descricao_trabalho: descricao_trabalho || '',
        mes: currentMonth,
        ano: currentYear
      });
    } catch (err) {
      console.error(err);
      setError("Erro ao adicionar entrega.");
    }
  };

  const handleDeleteEntrega = async (id: string) => {
    if (confirmingDeleteId !== id) {
      setConfirmingDeleteId(id);
      setTimeout(() => setConfirmingDeleteId(null), 3000); // Reset after 3 seconds
      return;
    }
    try {
      await deleteDoc(doc(db, 'atividades', id));
      setConfirmingDeleteId(null);
    } catch (err) {
      console.error(err);
      setError("Erro ao excluir entrega.");
    }
  };

  const handleAddUnidade = async () => {
    if (!newUnidade.trim()) return;
    try {
      await addDoc(collection(db, 'unidades'), { nome: newUnidade.trim() });
      setNewUnidade('');
    } catch (err) {
      console.error(err);
      setError("Erro ao adicionar unidade.");
    }
  };

  const handleDeleteUnidade = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'unidades', id));
    } catch (err) {
      console.error(err);
      setError("Erro ao excluir unidade.");
    }
  };

  const handleBatchImport = async (text: string) => {
    try {
      const lines = text.split('\n');
      const batchPromises = lines.map(line => {
        const [desc, date, entregaName] = line.split('\t');
        if (!desc || !date) return null;
        
        const entrega = entregas.find(e => e.entrega.includes(entregaName)) || entregas[0];
        
        return addDoc(collection(db, 'atividades_pgc'), {
          descricao_atividade: desc.trim(),
          data_inicio: date.trim(),
          entrega_id: entrega?.id || 'manual',
          status_atividade: 'concluida'
        });
      }).filter(p => !!p);

      await Promise.all(batchPromises);
      setIsBatchImportOpen(false);
    } catch (err) {
      console.error(err);
      setError("Erro na importação em lote.");
    }
  };

  const copyDeliveriesFromPreviousMonth = async () => {
    try {
      const prevMonth = currentMonth === 0 ? 11 : currentMonth - 1;
      const prevYear = currentMonth === 0 ? currentYear - 1 : currentYear;
      
      const prevDeliveries = entregas.filter(e => e.mes === prevMonth && e.ano === prevYear);
      if (prevDeliveries.length === 0) {
        setError("Nenhuma entrega encontrada no mês anterior.");
        return;
      }

      const batchPromises = prevDeliveries.map(e => {
        const { id, ...data } = e;
        return addDoc(collection(db, 'atividades'), {
          ...data,
          mes: currentMonth,
          ano: currentYear
        });
      });

      await Promise.all(batchPromises);
    } catch (err) {
      console.error(err);
      setError("Erro ao copiar entregas.");
    }
  };

  useEffect(() => {
    setLoading(true);
    setError(null);

    // Listener para Tarefas
    const qTarefas = query(collection(db, 'tarefas'));
    const unsubscribeTarefas = onSnapshot(qTarefas, (snapshot) => {
      const dataT = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as Tarefa));
      setTarefas(dataT);
      setLastSync(new Date());
      setLoading(false);
    }, (err) => {
      console.error(err);
      setError("Erro ao conectar com o banco de dados (Tarefas).");
      setLoading(false);
    });

    // Listener para Atividades PGC
    const qAtividadesPGC = query(collection(db, 'atividades_pgc'));
    const unsubscribeAtividadesPGC = onSnapshot(qAtividadesPGC, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as AtividadeRealizada));
      setAtividadesPGC(data);
    });

    // Listener para Afastamentos
    const qAfastamentos = query(collection(db, 'afastamentos'));
    const unsubscribeAfastamentos = onSnapshot(qAfastamentos, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as Afastamento));
      setAfastamentos(data);
    });

    // Listener para Atividades (Entregas Legado/Config)
    const qAtividades = query(collection(db, 'atividades'));
    const unsubscribeAtividades = onSnapshot(qAtividades, (snapshot) => {
      const dataE = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as EntregaInstitucional));
      setEntregas(dataE);
    }, (err) => {
      console.error(err);
      setError("Erro ao conectar com o banco de dados (Atividades).");
    });


    // Listener para Unidades
    const qUnidades = query(collection(db, 'unidades'));
    const unsubscribeUnidades = onSnapshot(qUnidades, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as {id: string, nome: string}));
      setUnidades(data);
    });

    return () => { 
      unsubscribeTarefas(); 
      unsubscribeAtividades();
      unsubscribeAtividadesPGC();
      unsubscribeAfastamentos();
      unsubscribeUnidades();
    };
  }, []);


  const handleLinkTarefa = async (tarefaId: string, entregaId: string) => {
    try {
      const docRef = doc(db, 'tarefas', tarefaId);
      await updateDoc(docRef, {
        entregas_relacionadas: [entregaId]
      });
    } catch (err) {
      console.error(err);
      setError("Erro ao vincular tarefa.");
    }
  };

  const stats = useMemo(() => ({
    total: tarefas.length,
    pendentes: tarefas.filter(t => normalizeStatus(t.status) === 'pendente').length,
    emAndamento: tarefas.filter(t => normalizeStatus(t.status) === 'em andamento').length,
    concluidas: tarefas.filter(t => normalizeStatus(t.status) === 'concluido').length,
    bloqueadas: tarefas.filter(t => normalizeStatus(t.status) === 'bloqueado').length,
  }), [tarefas]);

  const filteredAndSortedTarefas = useMemo(() => {
    let result = [...tarefas];
    if (searchTerm) {
      const s = searchTerm.toLowerCase();
      result = result.filter(t => t.titulo?.toLowerCase().includes(s) || t.projeto?.toLowerCase().includes(s));
    }
    if (statusFilter.length > 0) {
      result = result.filter(t => statusFilter.some(sf => normalizeStatus(t.status) === normalizeStatus(sf)));
    }
    
    result.sort((a, b) => {
      const dVal = (t: Tarefa) => (!t.data_limite || t.data_limite === "-" || t.data_limite.trim() === "") ? (sortOption === 'date-asc' ? Infinity : -Infinity) : new Date(t.data_limite).getTime();
      if (sortOption === 'date-asc') return dVal(a) - dVal(b);
      if (sortOption === 'date-desc') return dVal(b) - dVal(a);
      return 0;
    });
    return result;
  }, [tarefas, searchTerm, statusFilter, sortOption]);

  const tarefasAgrupadas = useMemo(() => {
    const groups: Record<string, Tarefa[]> = {};
    const now = new Date();
    now.setHours(0,0,0,0);
    const todayStr = now.toISOString().split('T')[0];
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];

    filteredAndSortedTarefas.forEach(t => {
      let label = "";
      if (!t.data_limite || t.data_limite === "-" || t.data_limite === "0000-00-00") {
        label = "Sem Data";
      } else if (t.data_limite === todayStr) {
        label = "Hoje";
      } else if (t.data_limite === tomorrowStr) {
        label = "Amanhã";
      } else {
        const parts = t.data_limite.split('-');
        const date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
        const dayOfWeek = new Intl.DateTimeFormat('pt-BR', { weekday: 'long' }).format(date);
        const capitalizedDay = dayOfWeek.charAt(0).toUpperCase() + dayOfWeek.slice(1);
        label = `${parts[2]}/${parts[1]}/${parts[0]} - ${capitalizedDay}`;
      }

      if (!groups[label]) groups[label] = [];
      groups[label].push(t);
    });
    return groups;
  }, [filteredAndSortedTarefas]);

  useEffect(() => {
    if (!hasAutoExpanded && Object.keys(tarefasAgrupadas).length > 0) {
      setExpandedSections([Object.keys(tarefasAgrupadas)[0]]);
      setHasAutoExpanded(true);
    }
  }, [tarefasAgrupadas, hasAutoExpanded]);

  const toggleSection = (label: string) => {
    setExpandedSections(prev => 
      prev.includes(label) ? prev.filter(s => s !== label) : [...prev, label]
    );
  };

  // No PGC, filtramos as tarefas pelo período selecionado (mês/ano)
  // No PGC, filtramos as tarefas pelo período selecionado (mês/ano)
  const pgcTasks = useMemo(() => {
    // Normalização agressiva para comparação de texto
    const norm = (val: any) => {
      if (!val) return "";
      return String(val).toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
    };

    return tarefas.filter(t => {
      const proj = norm(t.projeto);
      
      // Identificadores das unidades PGD/PGC - APENAS PELO CAMPO UNIDADE (projeto)
      const isCLC = proj.includes('CLC');
      const isASSIST = proj.includes('ASSIST') || proj.includes('ESTUDANTIL') || proj.includes('ANTIU');
      const isPgcUnit = isCLC || isASSIST;
      
      // Verifica se está vinculada a qualquer entrega institucional
      const linkedIds = Array.isArray(t.entregas_relacionadas) ? t.entregas_relacionadas.filter(id => !!id) : [];
      const isLinkedAtAll = linkedIds.length > 0;

      // Regra fundamental: Se não é unidade PGD e não foi vinculado manualmente, não entra no PGC
      if (!isPgcUnit && !isLinkedAtAll) return false;

      // Se estiver vinculado, aplicamos a regra de exibição temporal (mês atual)
      if (isLinkedAtAll) {
        if (!t.data_limite || t.data_limite === "-" || t.data_limite === "0000-00-00") return true; 
        const parts = t.data_limite.split(/[-/]/);
        if (parts.length < 3) return true;
        
        let taskYear = parseInt(parts[0]);
        let taskMonth = parseInt(parts[1]) - 1;
        
        if (taskYear < 1000) {
          taskYear = parseInt(parts[2]);
          taskMonth = parseInt(parts[1]) - 1;
        }
        
        return taskMonth === currentMonth && taskYear === currentYear;
      }

      // Se for unidade PGD mas ainda não vinculado, aparece no PGC (staging area)
      return isPgcUnit;
    });
  }, [tarefas, currentMonth, currentYear]);

  const pgcEntregas = useMemo(() => entregas.filter(e => {
    return e.mes === currentMonth && e.ano === currentYear;
  }), [entregas, currentMonth, currentYear]);

  const pgcTasksAguardando = useMemo(() => {
    const currentDeliveryIds = pgcEntregas.map(e => e.id);
    const norm = (val: any) => (val || '').toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
    
    return pgcTasks.filter(t => {
      const proj = norm(t.projeto);
      const isPgcUnit = proj.includes('CLC') || proj.includes('ASSIST') || proj.includes('ESTUDANTIL') || proj.includes('ANTIU');
      const linkedIds = Array.isArray(t.entregas_relacionadas) ? t.entregas_relacionadas : [];
      const isLinkedToCurrentDeliveries = linkedIds.some(id => currentDeliveryIds.includes(id));
      
      // Só aparece no "Aguardando Vínculo" se for de uma unidade PGD/PGC 
      // E não estiver vinculado a nenhuma entrega EXIBIDA no mês atual.
      return isPgcUnit && !isLinkedToCurrentDeliveries;
    });
  }, [pgcTasks, pgcEntregas]);

  const allUnidades = useMemo(() => {
    const fixed = ['CLC', 'Assistência Estudantil'];
    const dbUnidades = unidades.map(u => u.nome);
    return Array.from(new Set([...fixed, ...dbUnidades]));
  }, [unidades]);

  // Auditoria PGC - Heatmap de lacunas de registro
  const pgcAudit = useMemo(() => {
    const now = new Date();
    const workDays = getMonthWorkDays(currentYear, currentMonth);
    const gaps: Date[] = [];

    workDays.forEach(day => {
      // Ignorar dias futuros
      if (day > now) return;

      const dayStr = day.toISOString().split('T')[0];
      
      const hasActivity = atividadesPGC.some(a => {
        const start = a.data_inicio.split('T')[0];
        const end = a.data_fim?.split('T')[0] || start;
        return dayStr >= start && dayStr <= end;
      });

      const isAfastado = afastamentos.some(af => {
        const start = af.data_inicio.split('T')[0];
        const end = af.data_fim.split('T')[0];
        return dayStr >= start && dayStr <= end;
      });

      if (!hasActivity && !isAfastado) gaps.push(new Date(day));
    });

    return { gaps, totalWorkDays: workDays.length };
  }, [atividadesPGC, afastamentos]);

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col relative">

      <header className="bg-white border-b border-slate-200 sticky top-0 z-40 px-4 md:px-8 py-4 shadow-sm">
        <div className="max-w-[1400px] mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 bg-slate-900 rounded-xl flex items-center justify-center shadow-lg">
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
              </div>
              <h1 className="text-xl font-black tracking-tighter text-slate-900 hidden sm:block">HERMES</h1>
            </div>
            <nav className="flex bg-slate-100 p-1 rounded-xl border border-slate-200">
              <button onClick={() => setViewMode('gallery')} className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'gallery' ? 'bg-white text-slate-900 shadow-sm border border-slate-100' : 'text-slate-500 hover:text-slate-800'}`}>Geral</button>
              <button onClick={() => setViewMode('pgc')} className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'pgc' ? 'bg-slate-900 text-white shadow-lg' : 'text-slate-500 hover:text-slate-800'}`}>PGC</button>
            </nav>
          </div>

          <div className="flex items-center gap-4">
            <div className="hidden lg:flex items-center bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 w-64 group focus-within:ring-2 focus-within:ring-blue-500 focus-within:bg-white transition-all">
              <svg className="w-4 h-4 text-slate-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
              <input type="text" placeholder="Pesquisar..." className="bg-transparent border-none outline-none text-xs font-bold text-slate-900 w-full" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
            </div>

            <button 
              onClick={() => setIsSettingsOpen(true)}
              className="w-10 h-10 bg-white border border-slate-200 rounded-xl flex items-center justify-center text-slate-400 hover:text-slate-900 hover:border-slate-400 transition-all shadow-sm"
              title="Configurações"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-[1400px] mx-auto w-full px-0 md:px-8 py-6">
        {/* Painel de Estatísticas e Filtros - APENAS NA VISÃO GERAL */}
        {viewMode === 'gallery' && (
          <>
            <div className="px-4 md:px-0 grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
              {[ 
                { label: 'Total', value: stats.total, color: 'text-slate-900' }, 
                { label: 'Aberto', value: stats.pendentes, color: 'text-slate-500' }, 
                { label: 'Execução', value: stats.emAndamento, color: 'text-blue-600' }, 
                { label: 'Concluído', value: stats.concluidas, color: 'text-emerald-600' }, 
                { label: 'Bloqueado', value: stats.bloqueadas, color: 'text-rose-600' } 
              ].map((stat, i) => (
                <div key={i} className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col items-center justify-center text-center">
                  <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">{stat.label}</span>
                  <span className={`text-2xl font-black ${stat.color}`}>{stat.value}</span>
                </div>
              ))}
            </div>

            <div className="px-4 md:px-0 mb-6 flex flex-col md:flex-row items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <button 
                  onClick={() => setIsPanelExpanded(!isPanelExpanded)}
                  className="px-6 py-2.5 bg-white border border-slate-200 text-slate-900 rounded-xl flex items-center gap-3 font-black text-[10px] uppercase tracking-widest hover:border-slate-400 transition-all shadow-sm"
                >
                  <svg className={`w-4 h-4 transition-transform ${isPanelExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" /></svg>
                  Filtros
                </button>
                <button 
                  onClick={() => setIsAddTaskOpen(true)}
                  className="px-6 py-2 bg-slate-900 text-white rounded-xl flex items-center gap-3 font-black text-[10px] uppercase tracking-widest hover:bg-slate-800 transition-all shadow-md active:scale-95"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M12 4v16m8-8H4" /></svg>
                  Nova Atividade
                </button>
                {error && <span className="text-rose-600 text-[10px] font-black uppercase animate-pulse">{error}</span>}
              </div>

              <div className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl px-4 py-1.5 shadow-sm">
                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Ordem:</label>
                <select 
                  value={sortOption} 
                  onChange={(e) => setSortOption(e.target.value as any)} 
                  className="bg-transparent text-[10px] font-black uppercase outline-none cursor-pointer text-slate-900 pr-2"
                >
                  <option value="date-asc">Data ↑</option>
                  <option value="date-desc">Data ↓</option>
                </select>
              </div>
            </div>

            {/* Painel Expandido de Status */}
            {isPanelExpanded && (
              <div className="mx-4 md:mx-0 bg-white p-6 rounded-2xl border border-slate-200 shadow-lg mb-8 animate-in origin-top">
                <div className="flex flex-col md:flex-row md:items-center gap-6">
                  <div className="flex-1">
                    <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest block mb-3">Filtrar por Status</label>
                    <div className="flex flex-wrap gap-2">
                      {(['pendente', 'em andamento', 'concluído', 'bloqueado'] as Status[]).map(s => (
                        <FilterChip key={s} label={s} isActive={statusFilter.includes(s)} onClick={() => setStatusFilter(prev => prev.includes(s) ? prev.filter(v => v !== s) : [...prev, s])} />
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        <main className="mb-20">
          <div className="px-0">
            {viewMode === 'gallery' ? (
              <div className="animate-in border border-slate-200 overflow-hidden shadow-2xl bg-white">
                {Object.keys(tarefasAgrupadas).length > 0 ? (
                  Object.entries(tarefasAgrupadas).map(([label, tasks]) => (
                    <div key={label} className="border-b last:border-b-0 border-slate-200">
                      <button 
                        onClick={() => toggleSection(label)}
                        className="w-full px-8 py-5 bg-slate-50 border-b border-slate-200 flex items-center justify-between hover:bg-slate-100 transition-colors group"
                      >
                        <div className="flex items-center gap-4">
                          <div className={`w-2 h-8 rounded-full ${label === 'Hoje' ? 'bg-blue-600' : 'bg-slate-300'}`}></div>
                          <span className="text-sm font-black text-slate-900 uppercase tracking-[0.2em]">{label}</span>
                          <span className="bg-white border border-slate-200 text-[10px] font-black px-2 py-0.5 rounded-md text-slate-500">{tasks.length}</span>
                        </div>
                        <svg className={`w-5 h-5 text-slate-400 transition-transform duration-300 ${expandedSections.includes(label) ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>
                      
                      {expandedSections.includes(label) && (
                        <div className="animate-in origin-top">
                          {tasks.map(task => <RowCard key={task.id} task={task} onClick={setSelectedTask} />)}
                        </div>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="py-24 text-center bg-white">
                    <p className="text-slate-300 font-black text-xl uppercase tracking-widest">Sem demandas encontradas</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="animate-in space-y-10">
                {/* Cabeçalho Simplificado PGC */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 bg-white p-8 rounded-[2rem] border border-slate-200 shadow-xl">
                  <div>
                    <h3 className="text-4xl font-black text-slate-900 tracking-tighter">Gestão PGC</h3>
                    <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">{new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(new Date(currentYear, currentMonth))}</p>
                  </div>
                  <div className="flex items-center gap-4">
                    <select 
                      value={currentMonth} 
                      onChange={(e) => setCurrentMonth(Number(e.target.value))}
                      className="text-[10px] font-black uppercase bg-slate-100 px-4 py-2 rounded-xl border-none outline-none focus:ring-2 focus:ring-slate-900"
                    >
                      {['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'].map((m, i) => (
                        <option key={i} value={i}>{m}</option>
                      ))}
                    </select>
                    <button onClick={() => setIsAddActivityOpen(true)} className="bg-slate-900 text-white px-6 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-600 transition-all">Nova Atividade</button>
                    {pgcEntregas.length === 0 && (
                      <button onClick={copyDeliveriesFromPreviousMonth} className="px-6 py-2 bg-blue-50 text-blue-600 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-100 transition-all border border-blue-100">Copiar Mês Anterior</button>
                    )}
                  </div>
                </div>

                {/* Navegação Subview */}
                <div className="flex border-b border-slate-200">
                  <button 
                    onClick={() => setPgcSubView('audit')}
                    className={`px-8 py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all border-b-4 ${pgcSubView === 'audit' ? 'border-slate-900 text-slate-900' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                  >
                    Resumo de Atividades
                  </button>
                  <button 
                    onClick={() => setPgcSubView('config')}
                    className={`px-8 py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all border-b-4 ${pgcSubView === 'config' ? 'border-slate-900 text-slate-900' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                  >
                    Gestão de Entregas
                  </button>
                </div>

                {/* Conteúdo Dinâmico PGC */}
                {pgcSubView === 'audit' ? (
                  <div className="space-y-12 pb-20">
                     {/* Demandas sem vínculo - Staging para PGC */}
                     {pgcTasksAguardando.length > 0 && (
                       <div className="bg-white border border-slate-200 p-8 rounded-[2rem] shadow-xl space-y-6">
                         <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                           <div>
                             <h4 className="text-xl font-black text-slate-900 tracking-tight">Demandas Pendentes de Vínculo</h4>
                             <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest">Arraste para uma entrega ou use o seletor para vincular ao PGC</p>
                           </div>
                           <span className="bg-slate-900 text-white text-[10px] font-black px-4 py-1.5 rounded-full">{pgcTasksAguardando.length}</span>
                         </div>
                         <div className="flex flex-wrap gap-4">
                           {pgcTasksAguardando.map(task => (
                             <div key={task.id} className="flex flex-col gap-2">
                               <PgcMiniTaskCard task={task} onClick={setSelectedTask} />
                               <select 
                                 onChange={(e) => handleLinkTarefa(task.id, e.target.value)}
                                 className="w-full bg-slate-50 border border-slate-200 text-[8px] font-black uppercase px-2 py-1.5 rounded-lg outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
                               >
                                 <option value="">Vincular...</option>
                                 {pgcEntregas.map(e => <option key={e.id} value={e.id}>{e.entrega}</option>)}
                               </select>
                             </div>
                           ))}
                         </div>
                       </div>
                     )}

                    {/* Lista Vertical de Entregas (Zonas de Drop) */}
                    <div className="bg-white rounded-[2rem] border border-slate-200 overflow-hidden divide-y divide-slate-100 shadow-xl">
                      {pgcEntregas.map(entrega => {
                        const atividadesRelacionadas = atividadesPGC.filter(a => a.entrega_id === entrega.id);
                        const tarefasRelacionadas = pgcTasks.filter(t => t.entregas_relacionadas?.includes(entrega.id));
                        
                        return (
                          <div 
                            key={entrega.id} 
                            onDragOver={(e) => {
                              e.preventDefault();
                              e.currentTarget.classList.add('bg-blue-50');
                            }}
                            onDragLeave={(e) => {
                              e.currentTarget.classList.remove('bg-blue-50');
                            }}
                            onDrop={(e) => {
                              e.preventDefault();
                              e.currentTarget.classList.remove('bg-blue-50');
                              const tarefaId = e.dataTransfer.getData('tarefaId');
                              if (tarefaId) handleLinkTarefa(tarefaId, entrega.id);
                            }}
                            className="group flex flex-col md:flex-row hover:bg-slate-50 transition-all border-l-4 border-transparent hover:border-blue-500"
                          >
                            <div className="md:w-1/3 p-6 border-b md:border-b-0 md:border-r border-slate-100 bg-slate-50/30">
                              <div className="flex items-center gap-3 mb-2">
                                <span className="text-[8px] font-black text-blue-600 uppercase tracking-widest">{entrega.area || 'CLC'}</span>
                                {entrega.processo_sei && <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest font-mono">SEI: {entrega.processo_sei}</span>}
                              </div>
                              <h4 className="text-sm font-black text-slate-900 tracking-tight leading-snug group-hover:text-blue-700 transition-all">{entrega.entrega}</h4>
                              
                              {entrega.descricao_trabalho && (
                                <p className="mt-2 text-[10px] font-medium text-slate-500 italic leading-relaxed line-clamp-2">
                                  {entrega.descricao_trabalho}
                                </p>
                              )}

                              <div className="flex items-center gap-2 mt-3 text-[10px] font-black text-slate-500">
                                <div className="w-1.5 h-1.5 bg-blue-500 rounded-full"></div>
                                {atividadesRelacionadas.length + tarefasRelacionadas.length} Registros
                              </div>
                            </div>
                            <div className="flex-1 p-6">
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {/* Atividades PGC puras */}
                                {atividadesRelacionadas.map(at => (
                                  <div key={at.id} className="p-3 rounded-xl bg-slate-50 border border-slate-100 hover:border-slate-200 transition-all">
                                    <p className="text-[8px] font-black text-slate-400 uppercase mb-1">{formatDate(at.data_inicio)}</p>
                                    <p className="text-[11px] font-bold text-slate-700 leading-tight">{at.descricao_atividade}</p>
                                  </div>
                                ))}
                                {tarefasRelacionadas.map(t => (
                                  <div 
                                    key={t.id} 
                                    onClick={() => setSelectedTask(t)}
                                    className="p-3 rounded-xl bg-blue-50/20 border border-blue-100 hover:border-blue-300 hover:bg-blue-50/40 transition-all cursor-pointer group/task"
                                  >
                                    <div className="flex items-center justify-between mb-1">
                                      <p className="text-[8px] font-black text-blue-400 uppercase">Tarefa Geral</p>
                                      <p className="text-[8px] font-black text-slate-400 uppercase">{formatDate(t.data_limite)}</p>
                                    </div>
                                    <p className="text-[11px] font-bold text-slate-700 leading-tight group-hover/task:text-blue-700">{t.titulo}</p>
                                  </div>
                                ))}
                                {atividadesRelacionadas.length === 0 && tarefasRelacionadas.length === 0 && (
                                  <div className="col-span-full py-4">
                                    <p className="text-slate-300 text-[8px] font-black uppercase tracking-widest italic">Aguardando registros...</p>
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>

                  </div>
                ) : pgcSubView === 'config' ? (
                  <div className="animate-in space-y-8 bg-white p-10 rounded-[2rem] border border-slate-200 shadow-xl">
                    <div className="flex items-center justify-between border-b border-slate-100 pb-6">
                      <div>
                        <h4 className="text-2xl font-black text-slate-900 tracking-tight">Configuração de Entregas Institucionais</h4>
                        <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">Cadastre ou remova as categorias de entregas para o mês de {new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth))}</p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                      {/* Cadastro Individual */}
                      <form onSubmit={(e) => {
                        e.preventDefault();
                        const formData = new FormData(e.currentTarget);
                        handleAddEntrega(formData.get('entrega') as string, formData.get('area') as string);
                        (e.currentTarget as HTMLFormElement).reset();
                      }} className="space-y-4 bg-slate-50 p-8 rounded-[2rem] border border-slate-100 h-full">
                        <h5 className="text-sm font-black text-slate-900 uppercase tracking-widest mb-4">Cadastro Individual</h5>
                        <div>
                          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-2">Nome da Entrega</label>
                          <input name="entrega" required placeholder="Digite o nome da entrega..." className="w-full bg-white border border-slate-200 rounded-xl p-3 text-sm text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 shadow-sm" />
                        </div>
                        <div>
                          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-2">Área Responsável</label>
                          <select name="area" className="w-full bg-white border border-slate-200 rounded-xl p-3 text-sm text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 shadow-sm">
                            <option value="CLC">CLC</option>
                            <option value="Assistência Estudantil">Assistência Estudantil</option>
                          </select>
                        </div>
                        <button type="submit" className="w-full bg-slate-900 text-white px-8 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-600 transition-all shadow-lg mt-4">Adicionar Entrega</button>
                      </form>

                      {/* Importação em Lote */}
                      <div className="space-y-4 bg-blue-50/50 p-8 rounded-[2rem] border border-blue-100 flex flex-col h-full">
                        <h5 className="text-sm font-black text-blue-900 uppercase tracking-widest mb-2">Importação em Lote (CLC)</h5>
                        <p className="text-blue-700 text-[10px] font-black uppercase tracking-widest font-bold">Cole uma lista (uma por linha) e aperte CTRL+ENTER</p>
                        <textarea 
                          placeholder="Cole o texto do Plano de Trabalho aqui..."
                          className="flex-1 w-full bg-white border border-blue-200 rounded-2xl p-6 text-sm text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 shadow-sm min-h-[150px] resize-none"
                          onKeyDown={async (e) => {
                            if (e.key === 'Enter' && e.ctrlKey) {
                              const text = e.currentTarget.value;
                              if (!text.trim()) return;
                              
                              const lines = text.split('\n').map(l => l.trim());
                              let importedCount = 0;

                              for (let i = 0; i < lines.length; i++) {
                                const line = lines[i];
                                
                                // Pattern 1: CLC-BSF / BSF-CAB
                                if (line === 'CLC-BSF' || line === 'BSF-CAB') {
                                  const area = line === 'CLC-BSF' ? 'CLC' : 'Assistência Estudantil';
                                  const entregaTitle = lines[i+1];
                                  let description = '';
                                  // Procurar descrição após a porcentagem
                                  for (let j = i + 2; j < i + 10 && j < lines.length; j++) {
                                    if (lines[j].includes('%')) {
                                      description = lines[j+1];
                                      break;
                                    }
                                  }
                                  if (entregaTitle) {
                                    await handleAddEntrega(entregaTitle, area, description);
                                    importedCount++;
                                  }
                                }
                                
                                // Pattern 2: Não vinculadas
                                if (line === 'Não vinculadas a entregas') {
                                  let description = '';
                                  for (let j = i + 1; j < i + 10 && j < lines.length; j++) {
                                    if (lines[j].includes('%')) {
                                      description = lines[j+1];
                                      break;
                                    }
                                  }
                                  await handleAddEntrega('Tarefas Operacionais Rotineiras', 'CLC', description);
                                  importedCount++;
                                }
                              }

                              if (importedCount === 0) {
                                // Fallback para lista simples se não detectar o padrão acima
                                const simpleLines = text.split('\n').filter(l => l.trim());
                                for (const line of simpleLines) {
                                  await handleAddEntrega(line, 'CLC');
                                  importedCount++;
                                }
                              }

                              e.currentTarget.value = '';
                              alert(`${importedCount} entregas identificadas e cadastradas!`);
                            }
                          }}
                        />
                      </div>
                    </div>

                    <div className="divide-y divide-slate-100 border border-slate-100 bg-white shadow-xl">
                      {pgcEntregas.length > 0 ? pgcEntregas.map(e => (
                        <div key={e.id} className="flex items-center justify-between p-6 hover:bg-slate-50 transition-all group">
                          <div className="max-w-[80%]">
                            <span className="text-[9px] font-black text-blue-600 uppercase tracking-widest mb-1 block">{e.area}</span>
                            <h5 className="text-sm font-black text-slate-900 mb-2">{e.entrega}</h5>
                            {e.descricao_trabalho && (
                              <p className="text-[10px] font-medium text-slate-500 italic leading-relaxed">
                                {e.descricao_trabalho}
                              </p>
                            )}
                          </div>
                          <button 
                            onClick={() => handleDeleteEntrega(e.id)}
                            className={`p-3 rounded-xl transition-all ${confirmingDeleteId === e.id ? 'text-rose-600 bg-rose-50 opacity-100 scale-110 shadow-sm' : 'text-slate-400 hover:text-rose-600 hover:bg-rose-50 opacity-0 group-hover:opacity-100'}`}
                            title={confirmingDeleteId === e.id ? "Clique novamente para confirmar" : "Excluir entrega"}
                          >
                            {confirmingDeleteId === e.id ? (
                              <svg className="w-5 h-5 animate-in zoom-in" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                            ) : (
                              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                            )}
                          </button>
                        </div>
                      )) : (
                        <div className="py-20 text-center">
                          <p className="text-slate-300 font-black text-sm uppercase tracking-widest">Nenhuma entrega cadastrada para este mês</p>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="py-20 text-center bg-white rounded-[2rem] border-2 border-dashed border-slate-200">
                    <div className="w-24 h-24 bg-slate-50 rounded-full flex items-center justify-center mx-auto mb-6">
                      <svg className="w-12 h-12 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
                    </div>
                    <p className="text-slate-400 font-black text-xl uppercase tracking-widest">Recurso Indisponível</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </main>
      </div>

      {/* Modal de Detalhes */}
      {(() => {
        const activeTask = tarefas.find(t => t.id === selectedTask?.id);
        if (!activeTask) return null;
        
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-md animate-in" onClick={() => setSelectedTask(null)}>
          <div className="bg-white w-full max-w-2xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]" onClick={e => e.stopPropagation()}>
            <div className="p-8 md:p-12 overflow-y-auto">
              <div className="flex justify-between items-start mb-8">
                <div className="flex gap-3">
                  <select 
                    value={activeTask.status} 
                    onChange={(e) => handleUpdateTarefa(activeTask.id, { status: e.target.value as Status })}
                    className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest border-2 outline-none focus:ring-2 focus:ring-slate-900 transition-all ${STATUS_COLORS[activeTask.status.toLowerCase()] || STATUS_COLORS['default']}`}
                  >
                    {['pendente', 'em andamento', 'concluído', 'bloqueado'].map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <button onClick={() => setSelectedTask(null)} className="p-2 hover:bg-slate-100 rounded-full transition-colors"><svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg></button>
              </div>

              <textarea 
                defaultValue={activeTask.titulo}
                onBlur={(e) => {
                  if (e.target.value !== activeTask.titulo) handleUpdateTarefa(activeTask.id, { titulo: e.target.value });
                }}
                className="w-full text-3xl font-black text-slate-900 mb-8 leading-tight bg-transparent border-none outline-none focus:ring-2 focus:ring-slate-100 rounded-lg p-2 resize-none"
                placeholder="Título da Tarefa"
                rows={2}
              />
              
              <div className="space-y-6 mb-10">
                <h3 className="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em] flex items-center gap-4">
                  Acompanhamento
                  <div className="flex-1 h-[1px] bg-slate-100"></div>
                </h3>
                
                {/* Novo Comentário */}
                <div className="flex gap-4 items-start mb-8">
                  <div className="w-4 h-4 rounded-full border-4 border-slate-200 mt-2"></div>
                  <div className="flex-1 space-y-3">
                    <textarea 
                      placeholder="Registrar andamento..." 
                      value={newNote}
                      onChange={(e) => setNewNote(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-slate-900 resize-none min-h-[100px]"
                    />
                    <button 
                      onClick={() => handleAddHistory(activeTask)}
                      disabled={!newNote.trim()}
                      className="px-6 py-2 bg-slate-900 text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-slate-800 disabled:opacity-50 transition-all"
                    >
                      Registrar
                    </button>
                  </div>
                </div>

                <div className="space-y-4">
                  {activeTask.acompanhamento && activeTask.acompanhamento.length > 0 ? (
                    activeTask.acompanhamento.map((log, idx) => (
                      <div key={idx} className="relative pl-8 pb-4 last:pb-0">
                        {idx !== activeTask.acompanhamento.length - 1 && <div className="absolute left-[7px] top-4 bottom-0 w-[2px] bg-slate-100"></div>}
                        <div className="absolute left-0 top-1.5 w-4 h-4 rounded-full border-4 border-white bg-slate-900 shadow-sm"></div>
                        <div className="bg-slate-50 p-5 rounded-xl border border-slate-100">
                          <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest mb-2">{formatDate(log.data)}</p>
                          <p className="text-sm font-bold text-slate-800 leading-relaxed whitespace-pre-wrap">{log.nota}</p>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="bg-slate-50 p-8 rounded-2xl border-2 border-dashed border-slate-200 text-center">
                      <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">Nenhum registro de acompanhamento</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 text-center border-t border-slate-100 pt-8">
                <div className="bg-white border border-slate-200 p-5 rounded-xl">
                  <p className="text-[10px] font-black text-slate-400 uppercase mb-1.5 tracking-widest">Unidade</p>
                  <select 
                    value={activeTask.projeto}
                    onChange={(e) => handleUpdateTarefa(activeTask.id, { projeto: e.target.value })}
                    className="w-full text-center text-sm font-black text-slate-900 bg-transparent border-none outline-none focus:ring-2 focus:ring-slate-100 rounded cursor-pointer appearance-none"
                  >
                    {allUnidades.map(u => <option key={u} value={u}>{u}</option>)}
                    {!allUnidades.includes(activeTask.projeto) && <option value={activeTask.projeto}>{activeTask.projeto}</option>}
                  </select>
                </div>
                <div className="bg-white border border-slate-200 p-5 rounded-xl">
                  <p className="text-[10px] font-black text-slate-400 uppercase mb-1.5 tracking-widest">Prazo Final</p>
                  <input 
                    type="date"
                    defaultValue={activeTask.data_limite}
                    onChange={(e) => handleUpdateTarefa(activeTask.id, { data_limite: e.target.value })}
                    className="w-full text-center text-sm font-black text-slate-900 bg-transparent border-none outline-none focus:ring-2 focus:ring-slate-100 rounded cursor-pointer"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      );
    })()}

      {/* Modal Registrar Atividade - Refatorado conforme Screenshot */}
      {isAddActivityOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-md animate-in">
          <div className="bg-[#f8fafc] w-full max-w-5xl rounded-3xl shadow-2xl overflow-hidden border border-slate-200">
            <div className="bg-white px-10 py-6 border-b border-slate-200">
              <h2 className="text-xl font-bold text-[#334155] tracking-tight">Registrar Nova Atividade</h2>
            </div>
            
            <form onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.currentTarget);
              handleSaveAtividade({
                descricao_atividade: formData.get('desc') as string,
                data_inicio: formData.get('period') as string,
                entrega_id: formData.get('entrega') as string,
                usuario: formData.get('user') as string,
                status_atividade: 'concluida'
              });
            }} className="p-10 space-y-8">
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
                <div className="space-y-2">
                  <label className="text-[13px] font-bold text-[#475569]">Usuário</label>
                  <select name="user" className="w-full bg-white border border-slate-200 rounded-xl p-3.5 text-sm text-[#1e293b] outline-none focus:ring-2 focus:ring-emerald-500 transition-all appearance-none shadow-sm cursor-pointer">
                    <option value="André Martini">André Martini</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-[13px] font-bold text-[#475569]">Entrega</label>
                  <select name="entrega" required className="w-full bg-white border border-slate-200 rounded-xl p-3.5 text-sm text-[#1e293b] outline-none focus:ring-2 focus:ring-emerald-500 transition-all appearance-none shadow-sm cursor-pointer">
                    {pgcEntregas.map(e => <option key={e.id} value={e.id}>{e.entrega}</option>)}
                  </select>
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-[13px] font-bold text-[#475569]">Descrição da Atividade</label>
                <textarea 
                  name="desc" 
                  required 
                  className="w-full bg-white border border-slate-200 rounded-xl p-4 text-sm text-[#1e293b] outline-none focus:ring-2 focus:ring-emerald-500 h-32 resize-none shadow-sm" 
                  placeholder="O que você fez?" 
                />
              </div>

              <div className="space-y-2">
                <label className="text-[13px] font-bold text-[#475569]">Período</label>
                <div className="relative">
                  <input 
                    type="date" 
                    name="period" 
                    defaultValue={new Date().toISOString().split('T')[0]}
                    required 
                    className="w-full bg-white border border-slate-200 rounded-xl p-3.5 text-sm text-[#1e293b] outline-none focus:ring-2 focus:ring-emerald-500 shadow-sm" 
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
                <button type="button" onClick={() => setIsAddActivityOpen(false)} className="px-6 py-2.5 text-slate-500 font-bold hover:text-slate-800 transition-all">Descartar</button>
                <button type="submit" className="bg-[#22c55e] hover:bg-[#16a34a] text-white px-8 py-2.5 rounded-xl font-bold shadow-lg shadow-emerald-200 transition-all">Salvar Registro</button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* Modal Criar Tarefa - Características do Modal de Edição */}
      {isAddTaskOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-md animate-in" onClick={() => setIsAddTaskOpen(false)}>
          <div className="bg-white w-full max-w-2xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]" onClick={e => e.stopPropagation()}>
            <form onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.currentTarget);
              handleCreateTarefa({
                titulo: formData.get('titulo') as string,
                projeto: formData.get('unidade') as string,
                data_limite: formData.get('prazo') as string,
                status: formData.get('status') as Status,
                prioridade: 'média'
              });
            }} className="p-8 md:p-12 overflow-y-auto">
              <div className="flex justify-between items-start mb-8">
                <div className="flex gap-3">
                  <select 
                    name="status"
                    defaultValue="pendente"
                    className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest border-2 outline-none focus:ring-2 focus:ring-slate-900 transition-all ${STATUS_COLORS['pendente']}`}
                  >
                    {['pendente', 'em andamento', 'concluído', 'bloqueado'].map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <button type="button" onClick={() => setIsAddTaskOpen(false)} className="p-2 hover:bg-slate-100 rounded-full transition-colors"><svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg></button>
              </div>

              <textarea 
                name="titulo"
                required
                autoFocus
                className="w-full text-3xl font-black text-slate-900 mb-8 leading-tight bg-transparent border-none outline-none focus:ring-2 focus:ring-slate-100 rounded-lg p-2 resize-none"
                placeholder="Título da Nova Atividade..."
                rows={2}
              />
              
              <div className="grid grid-cols-2 gap-4 text-center border-t border-slate-100 pt-8 mb-8">
                <div className="bg-white border border-slate-200 p-5 rounded-xl">
                  <p className="text-[10px] font-black text-slate-400 uppercase mb-1.5 tracking-widest">Unidade</p>
                  <select 
                    name="unidade"
                    className="w-full text-center text-sm font-black text-slate-900 bg-transparent border-none outline-none focus:ring-2 focus:ring-slate-100 rounded cursor-pointer appearance-none"
                  >
                    {allUnidades.map(u => <option key={u} value={u}>{u}</option>)}
                  </select>
                </div>
                <div className="bg-white border border-slate-200 p-5 rounded-xl">
                  <p className="text-[10px] font-black text-slate-400 uppercase mb-1.5 tracking-widest">Prazo Final</p>
                  <input 
                    name="prazo"
                    type="date"
                    required
                    defaultValue={new Date().toISOString().split('T')[0]}
                    className="w-full text-center text-sm font-black text-slate-900 bg-transparent border-none outline-none focus:ring-2 focus:ring-slate-100 rounded cursor-pointer"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3">
                <button type="button" onClick={() => setIsAddTaskOpen(false)} className="px-6 py-2.5 text-slate-500 font-bold hover:text-slate-800 transition-all uppercase text-[10px] tracking-widest">Descartar</button>
                <button type="submit" className="bg-slate-900 text-white px-8 py-2.5 rounded-xl font-bold shadow-lg hover:bg-slate-800 transition-all uppercase text-[10px] tracking-widest">Criar Atividade</button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* Modal de Configurações */}
      {isSettingsOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-md animate-in" onClick={() => setIsSettingsOpen(false)}>
          <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]" onClick={e => e.stopPropagation()}>
            <div className="p-8 border-b border-slate-100 flex justify-between items-center">
              <h2 className="text-xl font-black text-slate-900 tracking-tight uppercase">Configurações</h2>
              <button onClick={() => setIsSettingsOpen(false)} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            
            <div className="p-8 overflow-y-auto">
              <div className="mb-8">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em]">Gerenciar Unidades</h3>
                  <span className="text-[9px] font-bold text-slate-400 uppercase italic">Antiga "Russa"</span>
                </div>
                
                <div className="flex gap-2 mb-6">
                  <input 
                    type="text" 
                    placeholder="Nova unidade..." 
                    value={newUnidade}
                    onChange={(e) => setNewUnidade(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleAddUnidade()}
                    className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-slate-900"
                  />
                  <button 
                    onClick={handleAddUnidade}
                    className="px-4 bg-slate-900 text-white rounded-xl hover:bg-slate-800 transition-all shadow-md active:scale-95"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                  </button>
                </div>

                <div className="space-y-2">
                  {allUnidades.map(unidade => {
                    const isFixed = ['CLC', 'Assistência Estudantil'].includes(unidade);
                    const dbUnid = unidades.find(u => u.nome === unidade);
                    
                    return (
                      <div key={unidade} className="flex items-center justify-between p-4 bg-slate-50 rounded-xl border border-slate-100 group">
                        <span className={`text-xs font-black uppercase tracking-tight ${isFixed ? 'text-blue-600' : 'text-slate-700'}`}>
                          {unidade}
                          {isFixed && <span className="ml-2 text-[8px] bg-blue-100 text-blue-600 px-1.5 py-0.5 rounded uppercase tracking-widest">PGD</span>}
                        </span>
                        {!isFixed && dbUnid && (
                          <button 
                            onClick={() => handleDeleteUnidade(dbUnid.id)}
                            className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const container = document.getElementById('root');
if (container) {
  const root = createRoot(container);
  root.render(<App />);
}
