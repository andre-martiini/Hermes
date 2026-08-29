import React, { useState, useEffect, useMemo } from 'react';
import { httpsCallable } from 'firebase/functions';
import { collection, onSnapshot, addDoc, deleteDoc, updateDoc, doc, writeBatch, setDoc } from 'firebase/firestore';
import { db, functions } from '@/firebase';
import { ShoppingItem } from '@/types';
import {
  flagsResultantes,
  linhaFlag,
  linhasImportaveis,
  normalizeShoppingText,
} from '@/src/utils/shoppingTransitions';

type ShoppingAssistantAction = 'view' | 'create' | 'update' | 'delete' | 'import_batch' | 'clear_planning' | 'finalize';

interface ShoppingListToolProps {
  onBack: () => void;
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
  initialImportText?: string;
  initialView?: 'catalog' | 'planning' | 'shopping';
  initialSearchTerm?: string;
  assistantAction?: ShoppingAssistantAction;
  targetItemId?: string;
  targetItemName?: string;
  nome?: string;
  categoria?: string;
  quantidade?: string;
  unit?: string;
  isPlanned?: boolean;
  isPurchased?: boolean;
  ordem?: number;
  isEmbedded?: boolean;
}

interface AssistantMutationPreview {
  title: string;
  description: string;
  lines: string[];
  action: ShoppingAssistantAction;
  payload: Record<string, any>;
}

/** Itens que o servidor criou apontando um possivel duplicado ja cadastrado. */
const contarDuplicatas = (dados: { parecidos?: unknown[]; created?: Array<{ parecidos?: unknown[] }> } | null) => {
  if (!dados) return 0;
  const noLote = (dados.created || []).filter(item => (item.parecidos || []).length > 0).length;
  return noLote + ((dados.parecidos || []).length > 0 ? 1 : 0);
};

export const ShoppingListTool = ({
  onBack,
  showToast,
  initialImportText,
  initialView,
  initialSearchTerm,
  assistantAction,
  targetItemId,
  targetItemName,
  nome,
  categoria,
  quantidade,
  unit,
  isPlanned,
  isPurchased,
  ordem,
  isEmbedded,
}: ShoppingListToolProps) => {
  const [items, setItems] = useState<ShoppingItem[]>([]);
  const [view, setView] = useState<'catalog' | 'planning' | 'shopping'>(initialView || 'catalog');
  const [searchTerm, setSearchTerm] = useState(initialSearchTerm || '');
  const [newItemName, setNewItemName] = useState('');
  const [newItemCategoria, setNewItemCategoria] = useState('Geral');
  const [isImportModalOpen, setIsImportModalOpen] = useState(!!initialImportText);
  const [importText, setImportText] = useState(initialImportText || '');
  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [editingField, setEditingField] = useState<'nome' | 'categoria' | 'quantidade' | null>(null);
  const [editValue, setEditValue] = useState('');
  const [isPortalConfigOpen, setIsPortalConfigOpen] = useState(false);
  const [externalToken, setExternalToken] = useState('');
  const [pendingDeleteItemId, setPendingDeleteItemId] = useState<string | null>(null);
  const [isClearPlanningPending, setIsClearPlanningPending] = useState(false);
  const [isFinalizingConfirmOpen, setIsFinalizingConfirmOpen] = useState(false);
  const [exitingPurchasedIds, setExitingPurchasedIds] = useState<string[]>([]);
  const [isPurchasedSectionOpen, setIsPurchasedSectionOpen] = useState(false);
  const [assistantStatus, setAssistantStatus] = useState<'idle' | 'applying' | 'applied' | 'cancelled' | 'error'>('idle');
  const [assistantError, setAssistantError] = useState('');
  // O servidor devolve `detalhe` (o que de fato gravou) e, na importacao, os
  // `parecidos` de cada item criado. Descartar isso e mostrar um toast generico
  // deixava a duplicata de grafia — "muçarela" com "Mussarela" ja no cadastro —
  // acontecer em silencio justamente pela web, que e onde o usuario esta.
  const [assistantResultado, setAssistantResultado] = useState<{
    detalhe?: string;
    parecidos?: Array<{ item_id: string; nome: string; categoria: string }>;
    created?: Array<{ nome: string; parecidos?: Array<{ item_id: string; nome: string; categoria: string }> }>;
  } | null>(null);
  // Antes do primeiro snapshot o catalogo esta vazio, e todo card do copiloto
  // preve o efeito a partir dele: `create` mostraria criacao onde o servidor vai
  // reaproveitar item existente, e a importacao contaria como novo o que ja
  // existe. Confirmar so depois de carregar.
  const [catalogoCarregado, setCatalogoCarregado] = useState(false);

  useEffect(() => {
    const unsubscribe = onSnapshot(collection(db, 'shopping_items'), (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as ShoppingItem));
      setItems(data);
      setCatalogoCarregado(true);
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    const unsubscribe = onSnapshot(doc(db, 'public_configs', 'shopping_portal'), (docSnap) => {
      if (!docSnap.exists()) {
        setExternalToken('');
        return;
      }
      const data = docSnap.data() as { token?: string };
      setExternalToken(data.token || '');
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (initialView) setView(initialView);
  }, [initialView]);

  useEffect(() => {
    if (typeof initialSearchTerm === 'string') setSearchTerm(initialSearchTerm);
  }, [initialSearchTerm]);

  useEffect(() => {
    if (typeof initialImportText === 'string') {
      setImportText(initialImportText);
      setIsImportModalOpen(Boolean(initialImportText));
    }
  }, [initialImportText]);

  const generateExternalToken = async () => {
    try {
      const token = Math.random().toString(36).substring(2, 10) + Math.random().toString(36).substring(2, 10);
      await setDoc(doc(db, 'public_configs', 'shopping_portal'), { token }, { merge: true });
      showToast('Token externo gerado!', 'success');
    } catch (e) {
      console.error(e);
      showToast('Erro ao gerar token externo.', 'error');
    }
  };

  const copyExternalLink = async () => {
    if (!externalToken) {
      showToast('Gere um token antes de copiar o link.', 'info');
      return;
    }
    const link = `${window.location.origin}/compras-externas?token=${externalToken}`;
    try {
      await navigator.clipboard.writeText(link);
      showToast('Link externo copiado!', 'success');
    } catch (e) {
      console.error(e);
      showToast('Erro ao copiar link.', 'error');
    }
  };

  // --- Catalog actions ---
  const handleAddItem = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!newItemName.trim()) return;
    const existing = items.find(i => i.nome.toLowerCase() === newItemName.trim().toLowerCase());
    if (existing) { showToast('Item já cadastrado!', 'info'); setNewItemName(''); return; }

    try {
      await addDoc(collection(db, 'shopping_items'), {
        nome: newItemName.trim(),
        categoria: newItemCategoria.trim() || 'Geral',
        quantidade: '1',
        unit: 'un',
        isPlanned: false,
        isPurchased: false,
      });
      setNewItemName('');
      showToast('Item cadastrado!', 'success');
    } catch (e) {
      console.error(e);
      showToast('Erro ao salvar.', 'error');
    }
  };

  const handleDeleteItem = async (id: string) => {
    if (pendingDeleteItemId !== id) {
      setPendingDeleteItemId(id);
      window.setTimeout(() => setPendingDeleteItemId(current => current === id ? null : current), 3500);
      return;
    }
    try {
      await deleteDoc(doc(db, 'shopping_items', id));
      setPendingDeleteItemId(null);
    } catch (e) {
      showToast('Erro ao excluir.', 'error');
    }
  };

  const handleBatchImport = async () => {
    if (!importText.trim()) return;
    const lines = importText.split('\n').map(l => l.trim()).filter(l => l !== '');
    if (lines.length === 0) return;

    try {
      const batch = writeBatch(db);
      // Limit batch size if needed, but for now simplistic
      lines.forEach(line => {
        const [nome, cat] = line.split('|').map(s => s.trim());
        if (!nome) return;
        const exists = items.find(i => i.nome.toLowerCase() === nome.toLowerCase());
        if (!exists) {
          const ref = doc(collection(db, 'shopping_items'));
          batch.set(ref, {
            nome,
            categoria: cat || 'Geral',
            quantidade: '1',
            unit: 'un',
            isPlanned: false,
            isPurchased: false
          });
        }
      });
      await batch.commit();
      setImportText('');
      setIsImportModalOpen(false);
      showToast(`${lines.length} linhas processadas!`, 'success');
    } catch (e) {
      console.error(e);
      showToast('Erro na importação.', 'error');
    }
  };

  const startEdit = (id: string, field: 'nome' | 'categoria' | 'quantidade', val: string) => {
    setEditingItemId(id); setEditingField(field); setEditValue(val);
  };

  const commitEdit = async () => {
    if (!editingItemId || !editingField) return;
    try {
      await updateDoc(doc(db, 'shopping_items', editingItemId), { [editingField]: editValue });
      setEditingItemId(null); setEditingField(null); setEditValue('');
    } catch (e) {
      showToast('Erro ao atualizar.', 'error');
    }
  };

  // --- Planning actions ---
  const togglePlanned = async (id: string) => {
    const item = items.find(i => i.id === id);
    if (!item) return;
    try {
      await updateDoc(doc(db, 'shopping_items', id), { isPlanned: !item.isPlanned, isPurchased: false });
    } catch(e) { console.error(e); }
  };

  const updateQuantidade = async (id: string, val: string) => {
    try {
      await updateDoc(doc(db, 'shopping_items', id), { quantidade: val });
    } catch(e) { console.error(e); }
  };

  const handleUnplanAll = async () => {
    const planned = items.filter(i => i.isPlanned || i.isPurchased);
    if (planned.length === 0) return;
    try {
      const batch = writeBatch(db);
      planned.forEach(i => {
        batch.update(doc(db, 'shopping_items', i.id), { isPlanned: false, isPurchased: false });
      });
      await batch.commit();
      showToast('Planejamento limpo!', 'info');
    } catch (e) { showToast('Erro ao limpar.', 'error'); }
  };

  const handleClearPlanningClick = async () => {
    if (!isClearPlanningPending) {
      setIsClearPlanningPending(true);
      window.setTimeout(() => setIsClearPlanningPending(false), 3500);
      return;
    }
    setIsClearPlanningPending(false);
    await handleUnplanAll();
  };

  // --- Shopping actions ---
  const togglePurchased = async (id: string) => {
    const item = items.find(i => i.id === id);
    if (!item) return;
    try {
      if (!item.isPurchased) {
        setExitingPurchasedIds(prev => prev.includes(id) ? prev : [...prev, id]);
        window.setTimeout(async () => {
          try {
            await updateDoc(doc(db, 'shopping_items', id), { isPurchased: true });
          } finally {
            setExitingPurchasedIds(prev => prev.filter(itemId => itemId !== id));
          }
        }, 320);
        return;
      }
      await updateDoc(doc(db, 'shopping_items', id), { isPurchased: !item.isPurchased });
    } catch(e) { console.error(e); }
  };

  const finalizeShopping = async () => {
    const planned = items.filter(i => i.isPlanned || i.isPurchased);
    if (planned.length === 0) return;
    try {
      const batch = writeBatch(db);
      planned.forEach(i => {
        batch.update(doc(db, 'shopping_items', i.id), { isPlanned: false, isPurchased: false });
      });
      await batch.commit();
      setView('catalog');
      showToast('Compra finalizada! Lista reiniciada.', 'success');
    } catch(e) { showToast('Erro ao finalizar.', 'error'); }
  };

  // --- Memos ---
  const filteredCatalog = useMemo(() =>
    items.filter(i => i.nome.toLowerCase().includes(searchTerm.toLowerCase()) || i.categoria.toLowerCase().includes(searchTerm.toLowerCase()))
      .sort((a, b) => a.categoria.localeCompare(b.categoria) || a.nome.localeCompare(b.nome)),
    [items, searchTerm]);

  const groupedCatalog = useMemo(() => {
    const g: { [k: string]: ShoppingItem[] } = {};
    filteredCatalog.forEach(it => { if (!g[it.categoria]) g[it.categoria] = []; g[it.categoria].push(it); });
    return g;
  }, [filteredCatalog]);

  const plannedItems = useMemo(() =>
    items.filter(i => i.isPlanned).sort((a, b) => Number(a.isPurchased) - Number(b.isPurchased) || a.categoria.localeCompare(b.categoria)),
    [items]);

  const purchasedCount = plannedItems.filter(i => i.isPurchased).length;
  const pendingShoppingItems = useMemo(() => plannedItems.filter(i => !i.isPurchased), [plannedItems]);
  const purchasedShoppingItems = useMemo(() => plannedItems.filter(i => i.isPurchased), [plannedItems]);

  const categories = useMemo(() => {
    const cats = new Set(items.map(i => i.categoria));
    return Array.from(cats).sort();
  }, [items]);

  const assistantTargetItem = useMemo(() => {
    if (!assistantAction || !['update', 'delete'].includes(assistantAction)) return null;
    if (targetItemId) return items.find(item => item.id === targetItemId) || null;
    if (!targetItemName) return null;

    const normalizedTarget = normalizeShoppingText(targetItemName);
    const exact = items.find(item => normalizeShoppingText(item.nome) === normalizedTarget);
    if (exact) return exact;

    const partialMatches = items.filter(item => normalizeShoppingText(item.nome).includes(normalizedTarget));
    return partialMatches.length === 1 ? partialMatches[0] : null;
  }, [assistantAction, items, targetItemId, targetItemName]);

  const assistantPreview = useMemo<AssistantMutationPreview | null>(() => {
    if (!assistantAction || assistantAction === 'view') return null;

    if (assistantAction === 'import_batch') {
      const rawText = (initialImportText || '').trim();
      // Contar linha nao serve: o servidor descarta nome vazio e nome repetido
      // dentro do proprio texto. Como o resultado da callable e jogado fora e a
      // UI so mostra um toast generico, este card e a unica previsao que o
      // usuario ve — entao ele aplica a mesma regra de `_parse_linhas`.
      const { nomes: importaveis, descartadas } = linhasImportaveis(rawText);
      const jaNoCadastro = importaveis.filter((nome: string) =>
        items.some(item => normalizeShoppingText(item.nome) === normalizeShoppingText(nome))).length;
      const novos = importaveis.length - jaNoCadastro;
      const sobra = descartadas > 0
        ? ` ${descartadas} linha(s) ficam de fora: repetida(s) no texto ou sem nome.`
        : '';
      // Sem repassar `isPlanned`, o servidor aplica o padrao (planejar) e a
      // importacao so-para-o-cadastro que o schema anuncia nao existiria pela web.
      const planejaImportacao = isPlanned !== false;
      return {
        title: 'Importacao em lote proposta',
        description: importaveis.length === 0
          ? 'Nenhuma linha valida foi enviada para importacao.'
          : planejaImportacao
            ? `${importaveis.length} item(ns) entram no planejamento: ${novos} novo(s) e ${jaNoCadastro} que ja estava(m) no cadastro.${sobra}`
            : `${novos} item(ns) novo(s) entram so no cadastro, sem planejamento — nao aparecem na aba Comprar. ${jaNoCadastro} ja existia(m) e fica(m) como esta(o).${sobra}`,
        lines: importaveis.slice(0, 6),
        action: assistantAction,
        payload: {
          action: 'import_batch',
          importText: rawText,
          ...(isPlanned !== undefined ? { isPlanned } : {}),
        },
      };
    }

    if (assistantAction === 'clear_planning') {
      return {
        title: 'Limpeza de planejamento proposta',
        description: 'Os itens planejados ou comprados voltam a ficar sem planejamento. Nenhum item e excluido do cadastro.',
        lines: [`Itens afetados agora: ${items.filter(item => item.isPlanned || item.isPurchased).length}`],
        action: assistantAction,
        payload: { action: 'clear_planning' },
      };
    }

    if (assistantAction === 'finalize') {
      return {
        title: 'Finalizacao de compra proposta',
        description: 'A rodada de compras sera encerrada e os status de planejamento e compra serao limpos.',
        lines: [`Itens na rodada atual: ${items.filter(item => item.isPlanned || item.isPurchased).length}`],
        action: assistantAction,
        payload: { action: 'finalize' },
      };
    }

    if (assistantAction === 'create') {
      const nextNome = (nome || targetItemName || '').trim();
      const nextCategoria = (categoria || 'Geral').trim() || 'Geral';
      const nextQuantidade = String(quantidade || '1').trim() || '1';
      const nextUnit = String(unit || 'un').trim() || 'un';
      const nextIsPlanned = Boolean(isPlanned);
      const nextIsPurchased = Boolean(isPurchased);
      const jaCadastrado = items.find(item => normalizeShoppingText(item.nome) === normalizeShoppingText(nextNome));
      // Sobre item que ja existe `create` e aditivo, e marcar como comprado
      // arrasta o planejamento junto. Calcular o par pela regra do servidor e o
      // que impede o card de prometer um estado e o banco gravar outro.
      const finalCriar = flagsResultantes(
        jaCadastrado ?? { isPlanned: false, isPurchased: false },
        isPlanned, isPurchased, true,
      );
      const mostraPlanejado = jaCadastrado
        && (isPlanned !== undefined || finalCriar.planejado !== jaCadastrado.isPlanned);
      const mostraComprado = jaCadastrado
        && (isPurchased !== undefined || finalCriar.comprado !== jaCadastrado.isPurchased);
      return {
        title: 'Criacao de item proposta',
        description: !nextNome
          ? 'Falta o nome do item para criar.'
          : jaCadastrado
            ? `"${jaCadastrado.nome}" ja esta no cadastro: em vez de duplicar, o item atual recebe o que o copiloto informou.`
            : `O item "${nextNome}" sera criado na lista.`,
        lines: jaCadastrado
          ? [
              `Nome: ${jaCadastrado.nome}`,
              ...(categoria !== undefined ? [`Categoria: ${jaCadastrado.categoria} -> ${nextCategoria}`] : []),
              ...(quantidade !== undefined ? [`Quantidade: ${jaCadastrado.quantidade} -> ${nextQuantidade}`] : []),
              ...(unit !== undefined ? [`Unidade: ${jaCadastrado.unit} -> ${nextUnit}`] : []),
              ...(mostraPlanejado ? [linhaFlag('Planejado', jaCadastrado.isPlanned, finalCriar.planejado, true)] : []),
              ...(mostraComprado ? [linhaFlag('Comprado', jaCadastrado.isPurchased, finalCriar.comprado, true)] : []),
              ...(typeof ordem === 'number' ? [`Ordem: ${ordem}`] : []),
            ]
          : [
              `Nome: ${nextNome || 'Nao informado'}`,
              `Categoria: ${nextCategoria}`,
              `Quantidade: ${nextQuantidade}`,
              `Unidade: ${nextUnit}`,
              `Planejado: ${finalCriar.planejado ? 'Sim' : 'Nao'}`,
              `Comprado: ${finalCriar.comprado ? 'Sim' : 'Nao'}`,
              ...(typeof ordem === 'number' ? [`Ordem: ${ordem}`] : []),
            ],
        action: assistantAction,
        // So vai no payload o que o copiloto informou de fato. Nome ja
        // cadastrado reaproveita o item existente, e mandar o default da UI
        // apagaria a categoria, a quantidade ou a unidade que o usuario ajustou
        // na tela. Para item novo os mesmos defaults sao aplicados no servidor.
        payload: {
          action: 'create',
          nome: nextNome,
          ...(categoria !== undefined ? { categoria: nextCategoria } : {}),
          ...(quantidade !== undefined ? { quantidade: nextQuantidade } : {}),
          ...(unit !== undefined ? { unit: nextUnit } : {}),
          ...(isPlanned !== undefined ? { isPlanned: nextIsPlanned } : {}),
          ...(isPurchased !== undefined ? { isPurchased: nextIsPurchased } : {}),
          ...(typeof ordem === 'number' ? { ordem } : {}),
        },
      };
    }

    if (assistantAction === 'delete') {
      return {
        title: 'Exclusao de item proposta',
        description: assistantTargetItem
          ? `O item "${assistantTargetItem.nome}" sera removido da lista.`
          : 'Nao consegui localizar o item que o copiloto quer excluir.',
        lines: assistantTargetItem
          ? [
              `Categoria: ${assistantTargetItem.categoria}`,
              `Quantidade: ${assistantTargetItem.quantidade} ${assistantTargetItem.unit}`,
              `Planejado: ${assistantTargetItem.isPlanned ? 'Sim' : 'Nao'}`,
              `Comprado: ${assistantTargetItem.isPurchased ? 'Sim' : 'Nao'}`,
            ]
          : [`Item informado: ${targetItemName || targetItemId || 'Nao identificado'}`],
        action: assistantAction,
        payload: {
          action: 'delete',
          itemId: assistantTargetItem?.id || targetItemId || '',
        },
      };
    }

    const target = assistantTargetItem;
    const diffLines: string[] = [];
    const payload: Record<string, any> = { action: 'update', itemId: target?.id || targetItemId || '' };

    if (nome !== undefined) {
      diffLines.push(`Nome: ${target?.nome || '—'} -> ${nome}`);
      payload.nome = nome;
    }
    if (categoria !== undefined) {
      diffLines.push(`Categoria: ${target?.categoria || '—'} -> ${categoria}`);
      payload.categoria = categoria;
    }
    if (quantidade !== undefined) {
      diffLines.push(`Quantidade: ${target?.quantidade || '—'} -> ${quantidade}`);
      payload.quantidade = quantidade;
    }
    if (unit !== undefined) {
      diffLines.push(`Unidade: ${target?.unit || '—'} -> ${unit}`);
      payload.unit = unit;
    }
    if (isPlanned !== undefined || isPurchased !== undefined) {
      // Em `update` a flag pedida vale, mas arrasta a outra: desplanejar tira o
      // comprado, e marcar comprado planeja. As duas linhas saem do estado final
      // para o card nao mostrar so metade do efeito.
      const atualFlags = {
        isPlanned: Boolean(target?.isPlanned),
        isPurchased: Boolean(target?.isPurchased),
      };
      const finalFlags = flagsResultantes(atualFlags, isPlanned, isPurchased, false);
      if (isPlanned !== undefined || finalFlags.planejado !== atualFlags.isPlanned) {
        diffLines.push(linhaFlag('Planejado', atualFlags.isPlanned, finalFlags.planejado, false));
      }
      if (isPurchased !== undefined || finalFlags.comprado !== atualFlags.isPurchased) {
        diffLines.push(linhaFlag('Comprado', atualFlags.isPurchased, finalFlags.comprado, false));
      }
      if (isPlanned !== undefined) payload.isPlanned = isPlanned;
      if (isPurchased !== undefined) payload.isPurchased = isPurchased;
    }
    if (ordem !== undefined) {
      diffLines.push(`Ordem: ${target?.ordem ?? '—'} -> ${ordem}`);
      payload.ordem = ordem;
    }

    return {
      title: 'Atualizacao de item proposta',
      description: target
        ? `O item "${target.nome}" sera atualizado apos sua confirmacao.`
        : 'Nao consegui localizar com seguranca o item que o copiloto quer alterar.',
      lines: diffLines.length > 0 ? diffLines : ['Nenhum campo de alteracao foi informado.'],
      action: assistantAction,
      payload,
    };
  }, [assistantAction, assistantTargetItem, categoria, initialImportText, isPlanned, isPurchased, items, nome, ordem, quantidade, targetItemId, targetItemName, unit]);

  const canConfirmAssistantAction = useMemo(() => {
    if (!assistantPreview) return false;
    if (!catalogoCarregado) return false;
    if (assistantAction === 'create') return Boolean(assistantPreview.payload.nome);
    if (assistantAction === 'update' || assistantAction === 'delete') return Boolean(assistantPreview.payload.itemId);
    if (assistantAction === 'import_batch') return Boolean(assistantPreview.payload.importText);
    return true;
  }, [assistantAction, assistantPreview, catalogoCarregado]);

  const duplicatasProvaveis = useMemo(() => {
    if (!assistantResultado) return [];
    const pares: Array<{ nome: string; parecido: { item_id: string; nome: string; categoria: string } }> = [];
    (assistantResultado.created || []).forEach(item => {
      (item.parecidos || []).slice(0, 1).forEach(parecido => pares.push({ nome: item.nome, parecido }));
    });
    (assistantResultado.parecidos || []).slice(0, 1).forEach(parecido => {
      pares.push({ nome: String(assistantPreview?.payload?.nome || ''), parecido });
    });
    return pares;
  }, [assistantPreview, assistantResultado]);

  const applyAssistantAction = async () => {
    if (!assistantPreview || !canConfirmAssistantAction) return;
    setAssistantStatus('applying');
    setAssistantError('');

    try {
      const fn = httpsCallable(functions, 'mutateShoppingList');
      const resposta = await fn(assistantPreview.payload);
      const dados = (resposta?.data ?? {}) as NonNullable<typeof assistantResultado>;
      setAssistantResultado(dados);
      setAssistantStatus('applied');
      const duplicatas = contarDuplicatas(dados);
      showToast(
        duplicatas > 0
          ? `Aplicado, mas ${duplicatas} item(ns) podem ja existir com outro nome — veja o card.`
          : 'Alteracao aplicada na lista de compras.',
        duplicatas > 0 ? 'info' : 'success',
      );
    } catch (error: any) {
      console.error(error);
      const message = error?.message || 'Erro ao aplicar alteracao na lista.';
      setAssistantStatus('error');
      setAssistantError(message);
      showToast(message, 'error');
    }
  };

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 space-y-6 pb-32 px-2 md:px-0">
      {assistantPreview && (
        <div className="bg-amber-50 border border-amber-200 rounded-none-none shadow-none p-5 space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-amber-700">Validacao do Copiloto</p>
              <h3 className="text-lg font-bold text-slate-900">{assistantPreview.title}</h3>
              <p className="text-sm text-slate-600 font-medium mt-1">{assistantPreview.description}</p>
            </div>
            <div className={`px-3 py-1 rounded-none-none text-[10px] font-bold uppercase tracking-wider ${
              assistantStatus === 'applied'
                ? 'bg-emerald-100 text-emerald-700'
                : assistantStatus === 'cancelled'
                  ? 'bg-slate-200 text-slate-500'
                  : assistantStatus === 'error'
                    ? 'bg-rose-100 text-rose-600'
                    : 'bg-white text-amber-700 border border-amber-200'
            }`}>
              {assistantStatus === 'applied' ? 'Aplicado' : assistantStatus === 'cancelled' ? 'Cancelado' : assistantStatus === 'error' ? 'Erro' : 'Pendente'}
            </div>
          </div>

          <div className="space-y-2">
            {assistantPreview.lines.map(line => (
              <div key={line} className="bg-white/80 rounded-none-none px-4 py-3 text-sm font-semibold text-slate-700">
                {line}
              </div>
            ))}
          </div>

          {assistantError && (
            <div className="bg-rose-50 border border-rose-100 rounded-none-none px-4 py-3 text-sm font-semibold text-rose-600">
              {assistantError}
            </div>
          )}

          {assistantStatus === 'applied' && assistantResultado?.detalhe && (
            <div className="bg-white border border-emerald-100 rounded-none-none px-4 py-3 text-sm font-semibold text-slate-700">
              {assistantResultado.detalhe}
            </div>
          )}

          {assistantStatus === 'applied' && duplicatasProvaveis.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-none-none px-4 py-3 space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-wider text-amber-700">
                Pode ser duplicata do que ja existe
              </p>
              {duplicatasProvaveis.map(({ nome, parecido }) => (
                <p key={`${nome}-${parecido.item_id}`} className="text-sm font-semibold text-slate-700">
                  "{nome}" parece "{parecido.nome}" ({parecido.categoria})
                </p>
              ))}
              <p className="text-[11px] font-semibold text-amber-700">
                Nada foi unido automaticamente. Confira no Cadastro e apague o que sobrou, se for o caso.
              </p>
            </div>
          )}

          {assistantStatus === 'idle' && (
            <div className="flex gap-3">
              <button
                onClick={applyAssistantAction}
                disabled={!canConfirmAssistantAction}
                className="flex-1 py-3 rounded-none-none text-[10px] font-bold uppercase tracking-wider text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                Confirmar alteracao
              </button>
              <button
                onClick={() => setAssistantStatus('cancelled')}
                className="flex-1 py-3 rounded-none-none text-[10px] font-bold uppercase tracking-wider text-slate-500 bg-white border border-slate-200 hover:bg-slate-50 transition-all"
              >
                Cancelar
              </button>
            </div>
          )}
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
        {!isEmbedded && (
          <button onClick={onBack} className="w-12 h-12 bg-white rounded-none-none flex items-center justify-center text-slate-400 hover:text-slate-900 border border-slate-200 hover:border-slate-900 transition-all shadow-none">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
          </button>
        )}
        <div className="flex-1">
          <h2 className="text-2xl md:text-3xl font-mono font-bold uppercase tracking-tight text-slate-900">Lista de Compras</h2>
          <p className="text-slate-500 font-mono text-xs uppercase font-bold">{items.length} itens cadastrados · {plannedItems.length} planejados</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 w-full lg:w-auto">
          <button
            onClick={() => setIsPortalConfigOpen(prev => !prev)}
            className={`h-11 px-3 md:px-4 rounded-none-none border text-[9px] md:text-[10px] font-bold uppercase tracking-wider transition-all ${isPortalConfigOpen ? 'bg-slate-900 text-white border-slate-900 shadow-none' : 'bg-white text-slate-500 border-slate-200 hover:text-slate-800 hover:border-slate-300'}`}
          >
            Portal Externo
          </button>
          {/* Tab selector */}
          <div className="flex-1 min-w-0 flex bg-slate-100 p-1 rounded-none-none gap-0.5">
            {(['catalog', 'planning', 'shopping'] as const).map(tab => {
              const labels: Record<string, string> = { catalog: 'Cadastro', planning: 'Planejar', shopping: 'Comprar' };
              return (
                <button key={tab} onClick={() => setView(tab)}
                  className={`flex-1 px-2 md:px-4 py-2.5 rounded-none-none text-[9px] md:text-[10px] font-bold uppercase tracking-wider transition-all relative ${view === tab ? 'bg-white text-slate-900 shadow-none' : 'text-slate-400 hover:text-slate-600'}`}>
                  {labels[tab]}
                  {tab === 'planning' && plannedItems.length > 0 && (
                    <span className="absolute -top-1 -right-1 bg-blue-500 text-white text-[8px] font-bold w-4 h-4 rounded-none-none flex items-center justify-center">{plannedItems.length}</span>
                  )}
                  {tab === 'shopping' && purchasedCount > 0 && (
                    <span className="absolute -top-1 -right-1 bg-emerald-500 text-white text-[8px] font-bold w-4 h-4 rounded-none-none flex items-center justify-center">{purchasedCount}</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {isPortalConfigOpen && (
        <div className="bg-white rounded-none-none border border-slate-200 shadow-xl p-6 animate-in fade-in slide-in-from-top-2 duration-300">
          <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-4">Portal Externo da Lista</h3>
          <div className="flex flex-col md:flex-row gap-3">
            <input
              type="text"
              readOnly
              value={externalToken}
              placeholder="Nenhum token gerado"
              className="flex-1 bg-slate-50 border border-slate-200 rounded-none-none px-4 py-3 text-xs font-mono text-slate-700 outline-none"
            />
            <button onClick={generateExternalToken} className="bg-blue-600 text-white px-4 py-3 rounded-none-none text-[10px] font-bold uppercase tracking-wider hover:bg-blue-700 transition-all">
              Gerar Token
            </button>
          </div>
          <div className="mt-3 flex flex-col md:flex-row gap-3">
            <input
              type="text"
              readOnly
              value={externalToken ? `${window.location.origin}/compras-externas?token=${externalToken}` : ''}
              placeholder="Link externo aparecerá aqui"
              className="flex-1 bg-slate-50 border border-slate-200 rounded-none-none px-4 py-3 text-xs font-mono text-slate-700 outline-none"
            />
            <button onClick={copyExternalLink} className="bg-emerald-600 text-white px-4 py-3 rounded-none-none text-[10px] font-bold uppercase tracking-wider hover:bg-emerald-700 transition-all">
              Copiar Link
            </button>
          </div>
          <p className="text-[10px] text-slate-400 font-bold mt-3">
            O portal externo compartilha os mesmos itens e status de planejamento/compra em tempo real.
          </p>
        </div>
      )}

      {/* ===== CADASTRO ===== */}
      {view === 'catalog' && (
        <div className="space-y-6 animate-in fade-in duration-300">
          {/* Add form */}
          <div className="bg-white rounded-none-none border border-slate-200 shadow-xl p-6 space-y-4">
            <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Novo Item</h3>
            <form onSubmit={handleAddItem} className="flex flex-col md:flex-row md:items-center gap-3">
              <input
                type="text"
                placeholder="Nome do item..."
                className="w-full md:flex-[2] bg-slate-50 border border-slate-200 rounded-none-none px-5 py-3 text-slate-800 font-bold outline-none focus:ring-1 focus:ring-slate-400 transition-all"
                value={newItemName}
                onChange={e => setNewItemName(e.target.value)}
                autoFocus
              />
              <select
                className="w-full md:flex-1 bg-slate-50 border border-slate-200 rounded-none-none px-4 py-3 text-slate-700 font-bold outline-none focus:ring-1 focus:ring-slate-400 transition-all"
                value={newItemCategoria}
                onChange={e => setNewItemCategoria(e.target.value)}
              >
                {['Geral', 'Hortifruti', 'Carnes', 'Laticínios', 'Padaria', 'Bebidas', 'Limpeza', 'Higiene', 'Congelados', 'Grãos e Cereais', 'Snacks', 'Temperos', 'Pet', ...categories.filter(c => !['Geral', 'Hortifruti', 'Carnes', 'Laticínios', 'Padaria', 'Bebidas', 'Limpeza', 'Higiene', 'Congelados', 'Grãos e Cereais', 'Snacks', 'Temperos', 'Pet'].includes(c))].map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
                <option value="Nova...">+ Nova categoria</option>
              </select>
              <div className="flex items-center gap-3">
                <button type="submit" className="bg-blue-600 text-white h-12 w-12 rounded-none-none flex items-center justify-center hover:bg-blue-700 transition-all shadow-none active:scale-95 flex-shrink-0">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                </button>
                <button type="button" onClick={() => setIsImportModalOpen(true)} title="Importar em lote" className="h-12 w-12 rounded-none-none border border-slate-200 flex items-center justify-center text-slate-400 hover:text-blue-500 hover:border-blue-200 transition-all flex-shrink-0">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0l-4-4m4 4v12" /></svg>
                </button>
              </div>
            </form>
          </div>

          {/* Search */}
          <div className="bg-white border border-slate-200 rounded-none-none px-5 py-3 flex items-center gap-3 shadow-none focus-within:ring-2 focus-within:ring-blue-100 transition-all">
            <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
            <input type="text" placeholder="Buscar no catálogo..." className="flex-1 bg-transparent outline-none text-sm font-bold text-slate-700 placeholder:text-slate-300" value={searchTerm} onChange={e => setSearchTerm(e.target.value)} />
            {searchTerm && <button onClick={() => setSearchTerm('')} className="text-slate-300 hover:text-slate-500"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg></button>}
          </div>

          {/* Catalog list grouped */}
          {Object.keys(groupedCatalog).length === 0 ? (
            <div className="py-24 text-center text-slate-300">
              <svg className="w-16 h-16 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" /></svg>
              <p className="font-bold uppercase tracking-wider text-sm">Nenhum item cadastrado</p>
              <p className="text-xs font-medium mt-2 opacity-60">Adicione itens acima para começar</p>
            </div>
          ) : (
            <div className="space-y-4">
              {Object.entries(groupedCatalog).map(([cat, catItems]) => (
                <div key={cat}>
                  <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider pl-2 mb-2">{cat}</h4>
                  <div className="bg-white rounded-none-none border border-slate-200 shadow-none divide-y divide-slate-200 overflow-hidden">
                    {catItems.map(item => (
                      <div key={item.id} className="flex items-center gap-4 px-5 py-4 hover:bg-slate-50 transition-all group">
                        <div className="flex-1 min-w-0">
                          {editingItemId === item.id && editingField === 'nome' ? (
                            <input autoFocus value={editValue} onChange={e => setEditValue(e.target.value)}
                              onBlur={commitEdit} onKeyDown={e => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') { setEditingItemId(null); setEditingField(null); } }}
                              className="w-full bg-blue-50 border border-blue-200 rounded-none-none px-3 py-1 text-slate-800 font-bold outline-none" />
                          ) : (
                            <p onClick={() => startEdit(item.id, 'nome', item.nome)} className="font-mono font-bold text-slate-800 cursor-pointer hover:text-blue-600 transition-colors truncate">{item.nome}</p>
                          )}
                          {editingItemId === item.id && editingField === 'categoria' ? (
                            <input autoFocus value={editValue} onChange={e => setEditValue(e.target.value)}
                              onBlur={commitEdit} onKeyDown={e => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') { setEditingItemId(null); setEditingField(null); } }}
                              className="mt-0.5 w-32 bg-blue-50 border border-blue-200 rounded-none px-2 py-0.5 text-[10px] font-bold outline-none" />
                          ) : (
                            <p onClick={() => startEdit(item.id, 'categoria', item.categoria)} className="text-[10px] font-bold text-slate-400 uppercase tracking-wider cursor-pointer hover:text-blue-500 transition-colors mt-0.5">{item.categoria}</p>
                          )}
                        </div>
                        <button onClick={() => handleDeleteItem(item.id)} className={`opacity-100 md:opacity-0 md:group-hover:opacity-100 p-2 rounded-none-none transition-all ${pendingDeleteItemId === item.id ? 'bg-rose-500 text-white shadow-none' : 'text-slate-300 hover:text-rose-500 hover:bg-rose-50'}`}>
                          {pendingDeleteItemId === item.id ? (
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                          ) : (
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                          )}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ===== PLANEJAMENTO ===== */}
      {view === 'planning' && (
        <div className="space-y-6 animate-in fade-in duration-300">
          <div className="flex items-center gap-3">
            <div className="flex-1 bg-white border border-slate-200 rounded-none-none px-5 py-3 flex items-center gap-3 shadow-none focus-within:ring-2 focus-within:ring-blue-100 transition-all">
              <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
              <input type="text" placeholder="Filtrar itens..." className="flex-1 bg-transparent outline-none text-sm font-bold text-slate-700 placeholder:text-slate-300" value={searchTerm} onChange={e => setSearchTerm(e.target.value)} />
            </div>
            <button onClick={handleClearPlanningClick} title="Limpar planejamento" className={`group h-12 px-3 border rounded-none-none shadow-none flex items-center gap-2 transition-all ${isClearPlanningPending ? 'bg-rose-500 border-rose-600 text-white' : 'bg-white border-slate-200 text-slate-400 hover:text-rose-500 hover:border-rose-200 hover:bg-rose-50'}`}>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
              <span className="text-[8px] font-bold uppercase tracking-wider">{isClearPlanningPending ? 'Confirma limpeza' : 'Limpar Planejamento'}</span>
            </button>
          </div>

          {items.length === 0 ? (
            <div className="py-24 text-center text-slate-300">
              <p className="font-bold uppercase tracking-wider text-sm">Nenhum item no catálogo</p>
              <button onClick={() => setView('catalog')} className="mt-4 text-blue-500 text-[10px] font-bold uppercase tracking-wider hover:text-blue-600 transition-colors">Ir para o Cadastro →</button>
            </div>
          ) : (
            <div className="space-y-4">
              {Object.entries(groupedCatalog).map(([cat, catItems]) => (
                <div key={cat}>
                  <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider pl-2 mb-2">{cat}</h4>
                  <div className="bg-white rounded-none-none border border-slate-200 shadow-none divide-y divide-slate-200 overflow-hidden">
                    {catItems.map(item => (
                      <div key={item.id} className={`flex items-center gap-4 px-5 py-4 transition-all ${item.isPlanned ? 'bg-blue-50/40' : 'hover:bg-slate-50'}`}>
                        <button onClick={() => togglePlanned(item.id)}
                          className={`w-8 h-8 rounded-none-none flex items-center justify-center transition-all flex-shrink-0 ${item.isPlanned ? 'bg-blue-600 text-white shadow-none shadow-none' : 'bg-slate-100 text-slate-400 hover:bg-slate-200'}`}>
                          {item.isPlanned
                            ? <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                            : <div className="w-2 h-2 bg-slate-400 rounded-none-none" />}
                        </button>
                        <span className={`flex-1 font-bold text-sm ${item.isPlanned ? 'text-slate-900' : 'text-slate-400'}`}>{item.nome}</span>
                        {item.isPlanned && (
                          <div className="flex items-center gap-2 bg-white border border-blue-100 rounded-none-none px-3 py-1.5 shadow-none">
                            <button onClick={() => updateQuantidade(item.id, String(Math.max(0.5, parseFloat(item.quantidade || '1') - (parseFloat(item.quantidade || '1') % 1 === 0 ? 1 : 0.5))))}
                              className="w-6 h-6 rounded-none-none bg-slate-100 text-slate-600 font-bold flex items-center justify-center hover:bg-blue-100 transition-all text-sm leading-none">−</button>
                            {editingItemId === item.id && editingField === 'quantidade' ? (
                              <input autoFocus value={editValue} onChange={e => setEditValue(e.target.value)}
                                onBlur={commitEdit} onKeyDown={e => { if (e.key === 'Enter') commitEdit(); }}
                                className="w-12 text-center bg-transparent text-slate-800 font-bold text-sm outline-none" />
                            ) : (
                              <span onClick={() => startEdit(item.id, 'quantidade', item.quantidade)}
                                className="w-10 text-center text-slate-800 font-bold text-sm cursor-pointer hover:text-blue-600 transition-colors">
                                {item.quantidade} <span className="text-slate-400 font-medium text-[10px]">{item.unit}</span>
                              </span>
                            )}
                            <button onClick={() => updateQuantidade(item.id, String(parseFloat(item.quantidade || '1') + (parseFloat(item.quantidade || '1') % 1 === 0 ? 1 : 0.5)))}
                              className="w-6 h-6 rounded-none-none bg-slate-100 text-slate-600 font-bold flex items-center justify-center hover:bg-blue-100 transition-all text-sm leading-none">+</button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {plannedItems.length > 0 && (
            <div className="sticky bottom-6">
              <button onClick={() => setView('shopping')}
                className="w-full bg-blue-600 text-white py-4 rounded-none-none font-bold uppercase tracking-wider text-sm shadow-none shadow-none hover:bg-blue-700 transition-all active:scale-[0.98] flex items-center justify-center gap-3">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
                Ir às Compras · {plannedItems.length} itens
              </button>
            </div>
          )}
        </div>
      )}

      {/* ===== COMPRAS ===== */}
      {view === 'shopping' && (
        <div className="space-y-6 animate-in fade-in duration-300">
          {/* Progress bar */}
          <div className="bg-white rounded-none-none border border-slate-200 shadow-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-xl font-bold text-slate-900">Comprando</h3>
                <p className="text-slate-400 text-[10px] font-bold uppercase tracking-wider mt-0.5">{purchasedCount} de {plannedItems.length} comprados</p>
              </div>
              <button onClick={() => setIsFinalizingConfirmOpen(true)} className="bg-emerald-500 text-white px-6 py-3 rounded-none-none text-[10px] font-bold uppercase tracking-wider hover:bg-emerald-600 transition-all shadow-none shadow-none">Finalizar</button>
            </div>
            <div className="w-full bg-slate-100 rounded-none-none h-2 overflow-hidden">
              <div className="bg-emerald-500 h-2 rounded-none-none transition-all duration-500"
                style={{ width: plannedItems.length > 0 ? `${(purchasedCount / plannedItems.length) * 100}%` : '0%' }} />
            </div>
          </div>

          {plannedItems.length === 0 ? (
            <div className="py-24 text-center text-slate-300">
              <p className="font-bold uppercase tracking-wider text-sm">Lista vazia</p>
              <button onClick={() => setView('planning')} className="mt-4 text-blue-500 text-[10px] font-bold uppercase tracking-wider hover:text-blue-600 transition-colors">Ir para o Planejamento →</button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="bg-white rounded-none-none border border-slate-200 shadow-xl overflow-hidden">
                <div className="divide-y divide-slate-200">
                  {pendingShoppingItems.map(item => (
                    <div
                      key={item.id}
                      onClick={() => togglePurchased(item.id)}
                      className={`flex items-center gap-5 px-6 py-5 cursor-pointer transition-all duration-300 select-none hover:bg-slate-50 ${exitingPurchasedIds.includes(item.id) ? 'bg-emerald-50 opacity-40 scale-[0.98]' : ''}`}
                    >
                      <div className="w-10 h-10 rounded-none-none flex items-center justify-center transition-all flex-shrink-0 bg-slate-100 text-slate-400">
                        <div className="w-3 h-3 border-2 border-current rounded-none-none" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-lg font-mono font-bold uppercase tracking-tight text-slate-900">{item.nome}</p>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{item.categoria}</p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <span className="text-lg font-mono font-bold text-blue-600">{item.quantidade}</span>
                        <span className="text-slate-400 font-mono text-[10px] uppercase font-bold ml-1">{item.unit}</span>
                      </div>
                    </div>
                  ))}
                  {pendingShoppingItems.length === 0 && (
                    <div className="px-6 py-8 text-center text-slate-400">
                      <p className="text-sm font-bold uppercase tracking-wider">Tudo comprado</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="bg-white rounded-none-none border border-slate-200 shadow-xl overflow-hidden">
                <button
                  type="button"
                  onClick={() => setIsPurchasedSectionOpen(prev => !prev)}
                  className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-50 transition-colors"
                >
                  <div className="text-left">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Comprados</p>
                    <p className="text-sm font-bold text-slate-900">{purchasedShoppingItems.length} itens</p>
                  </div>
                  <svg className={`w-5 h-5 text-slate-400 transition-transform ${isPurchasedSectionOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {isPurchasedSectionOpen && (
                  <div className="divide-y divide-slate-200 border-t border-slate-200">
                    {purchasedShoppingItems.map(item => (
                      <div
                        key={item.id}
                        onClick={() => togglePurchased(item.id)}
                        className="flex items-center gap-5 px-6 py-5 cursor-pointer transition-all duration-300 select-none bg-slate-50/70 hover:bg-slate-100/70"
                      >
                        <div className="w-10 h-10 rounded-none-none flex items-center justify-center transition-all flex-shrink-0 bg-emerald-500 text-white shadow-none shadow-none">
                          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-base font-mono font-bold uppercase tracking-tight line-through text-slate-400">{item.nome}</p>
                          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{item.categoria}</p>
                        </div>
                        <div className="text-right flex-shrink-0">
                          <span className="text-lg font-mono font-bold text-slate-300">{item.quantidade}</span>
                          <span className="text-slate-400 font-mono text-[10px] uppercase font-bold ml-1">{item.unit}</span>
                        </div>
                      </div>
                    ))}
                    {purchasedShoppingItems.length === 0 && (
                      <div className="px-6 py-8 text-center text-slate-400">
                        <p className="text-sm font-bold uppercase tracking-wider">Nenhum item comprado ainda</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Import Modal */}
      {isImportModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
          <div className="bg-white w-full max-w-lg rounded-none-none shadow-none overflow-hidden animate-in zoom-in-95 duration-300">
            <div className="p-8 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="text-2xl font-bold text-slate-900 tracking-tight">Importação em Lote</h3>
                <p className="text-slate-400 text-[10px] font-bold uppercase tracking-wider mt-1">Um item por linha · Nome|Categoria (opcional)</p>
              </div>
              <button onClick={() => setIsImportModalOpen(false)} className="p-2 hover:bg-slate-100 rounded-none-none transition-colors">
                <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="p-8 space-y-4">
              <textarea autoFocus
                className="w-full bg-slate-50 border border-slate-200 rounded-none-none p-6 text-slate-800 font-bold leading-relaxed outline-none focus:ring-1 focus:ring-slate-400 transition-all min-h-[260px] resize-none"
                placeholder={"Exemplo:\nArroz|Grãos e Cereais\nFeijão|Grãos e Cereais\nLeite|Laticínios\nSabão|Limpeza"}
                value={importText}
                onChange={e => setImportText(e.target.value)}
              />
              <div className="flex gap-4">
                <button onClick={() => setIsImportModalOpen(false)} className="flex-1 py-4 text-[10px] font-bold uppercase tracking-wider text-slate-400 hover:bg-slate-50 rounded-none-none transition-all">Cancelar</button>
                <button onClick={handleBatchImport} className="flex-[2] py-4 bg-blue-600 text-white rounded-none-none text-[10px] font-bold uppercase tracking-wider shadow-none shadow-none hover:bg-blue-700 transition-all">
                  Importar {importText.split('\n').filter(l => l.trim()).length} Itens
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {isFinalizingConfirmOpen && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white w-full max-w-md rounded-none-none p-6 space-y-4 shadow-none">
            <h3 className="text-lg font-bold text-slate-900">Finalizar Compras</h3>
            <p className="text-sm text-slate-500 font-medium">Isto limpará os itens planejados/comprados desta rodada. Continuar?</p>
            <div className="flex gap-3">
              <button onClick={() => setIsFinalizingConfirmOpen(false)} className="flex-1 py-3 rounded-none-none text-[10px] font-bold uppercase tracking-wider text-slate-500 bg-slate-100 hover:bg-slate-200 transition-all">Cancelar</button>
              <button onClick={async () => { await finalizeShopping(); setIsFinalizingConfirmOpen(false); }} className="flex-1 py-3 rounded-none-none text-[10px] font-bold uppercase tracking-wider text-white bg-emerald-600 hover:bg-emerald-700 transition-all">Confirmar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
