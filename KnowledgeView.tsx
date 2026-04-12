import React, { useState, useMemo, useEffect, useRef } from 'react';
import { ConhecimentoItem, formatDate, Tarefa, WorkItem, BaseConhecimento, KnowledgeVersionEntry, KnowledgeEdge, RelationKind } from './types';
import { db } from './firebase';
import { collection, getDocs, limit, orderBy, query } from 'firebase/firestore';
import {
    addEdge,
    removeEdge,
    getEdgesForItem,
    isEdgeActive,
    RELATION_KIND_LABELS,
    RELATION_KIND_COLORS,
} from './src/utils/knowledgeGraph';
import {
    type KnowledgeSearchMode,
    ROOT_ACTIONS_FOLDER_ID,
    ROOT_HEALTH_FOLDER_ID,
    ROOT_PROJECTS_FOLDER_ID,
    computeFolderStructure,
    filterCurrentItems,
    getTaskIdFromActionFolderId,
    isActionDiaryItemId,
    isActionVirtualFolderId,
    isRootKnowledgeFolderId
} from './src/utils/knowledgeLogic';
import * as idb from 'idb-keyval';

import { AutoExpandingTextarea } from './src/components/ui/UIComponents';
import { KnowledgeGraphView } from './src/components/tools/KnowledgeGraphView';
import { GlobalKnowledgeGraph } from './src/components/tools/GlobalKnowledgeGraph';

interface KnowledgeViewProps {
    items: ConhecimentoItem[];
    knowledgeBases: BaseConhecimento[];
    onUploadFile: (file: File, destinationFolderId?: string | null, baseId?: string | null) => Promise<ConhecimentoItem | null> | Promise<void> | void;
    onAddLink?: (url: string, title: string, destinationFolderId?: string | null, baseId?: string | null) => Promise<void>;
    onSaveItem?: (item: Partial<ConhecimentoItem>) => Promise<void>;
    onRenameAction?: (taskId: string, title: string) => Promise<void>;
    onDeleteItem: (id: string) => void;
    onProcessWithAI?: (id: string) => Promise<any>;
    onGenerateSlides?: (text: string) => Promise<any>;
    onNavigateToOrigin?: (modulo: string, id: string) => void;
    onCreateBase: (nome: string) => Promise<void>;
    onUpdateBase: (id: string, updates: Partial<BaseConhecimento>) => Promise<void>;
    onDeleteBase: (id: string) => Promise<void>;
    allTasks?: Tarefa[];
    allWorkItems?: WorkItem[];
    masterKnowledge?: any[];
    showConfirm?: (title: string, message: string, onConfirm: () => void) => void;
}

const KnowledgeView: React.FC<KnowledgeViewProps> = ({ 
    items, 
    knowledgeBases = [], 
    onUploadFile, 
    onAddLink, 
    onSaveItem, 
    onRenameAction, 
    onDeleteItem, 
    onProcessWithAI,
    onGenerateSlides,
    onNavigateToOrigin,
    onCreateBase,
    onUpdateBase,
    onDeleteBase,
    allTasks = [], 
    allWorkItems = [], 
    masterKnowledge = [], 
    showConfirm 
}) => {
    const formatMemoryPath = (item: ConhecimentoItem) =>
        item.memory_location
            ? [item.memory_location.wing, item.memory_location.room, item.memory_location.drawer, item.memory_location.cabinet]
                .filter(Boolean)
                .join(' / ')
            : 'Não localizado';

    const isKnowledgeProcessingPending = (item: ConhecimentoItem) =>
        !item.is_folder && Boolean(item.texto_bruto) && item.intake_record?.processing_status !== 'vectorized';

    const getProcessingLabel = (item: ConhecimentoItem) => {
        const status = item.intake_record?.processing_status;
        switch (status) {
            case 'vectorized':
                return 'Vetorizado';
            case 'prepared':
                return 'Preparado';
            case 'processing':
                return 'Em processamento';
            case 'rejected':
                return 'Bloqueado';
            default:
                return item.texto_bruto ? 'Pronto para IA' : 'Bruto';
        }
    };

    const getProcessingTone = (item: ConhecimentoItem) => {
        const status = item.intake_record?.processing_status;
        switch (status) {
            case 'vectorized':
                return 'bg-emerald-100 text-emerald-700';
            case 'processing':
                return 'bg-amber-100 text-amber-700';
            case 'rejected':
                return 'bg-rose-100 text-rose-700';
            default:
                return 'bg-slate-100 text-slate-600';
        }
    };

    const formatUpdateReason = (reason?: string) => {
        switch (reason) {
            case 'human_edit':
                return 'Edição humana';
            case 'ocr_extraction':
                return 'Extração OCR';
            case 'vectorization':
                return 'Vetorização';
            case 'ingestion':
                return 'Ingestão';
            case 'system_sync':
                return 'Sincronização';
            default:
                return 'Não informado';
        }
    };

    const formatChangedFields = (fields?: string[]) => {
        if (!fields || fields.length === 0) return null;
        const labels: Record<string, string> = {
            titulo: 'título',
            texto_bruto: 'conteúdo',
            resumo_tldr: 'resumo',
            tags: 'tags',
            categoria: 'categoria',
            url_drive: 'arquivo',
            tipo_arquivo: 'tipo',
            base_id: 'base',
            parent_id: 'pasta',
            origem: 'origem',
        };
        return fields.map((f) => labels[f] ?? f).join(', ');
    };

    const formatOriginLabel = (item: ConhecimentoItem) => {
        if (item.intake_record?.source_refs?.length) {
            const primary = item.intake_record.source_refs[0];
            return primary.label || primary.filename || primary.id || primary.kind;
        }
        if (item.origem?.modulo && item.origem?.id_origem) {
            return `${item.origem.modulo}:${item.origem.id_origem}`;
        }
        return 'Não informado';
    };

    const [activeTab, setActiveTab] = useState<'library' | 'master'>('library');
    const [searchTerm, setSearchTerm] = useState('');
    const [searchMode, setSearchMode] = useState<KnowledgeSearchMode>('all');
    const [currentFolderId, setCurrentFolderId] = useState<string | null>(null);
    const [isMoveModalOpen, setIsMoveModalOpen] = useState(false);
    const [moveTargetFolderId, setMoveTargetFolderId] = useState<string | null>(null);
    const [selectedItem, setSelectedItem] = useState<ConhecimentoItem | null>(null);
    const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
    const [isGlobalGraphOpen, setIsGlobalGraphOpen] = useState(false);
    const [globalEdges, setGlobalEdges] = useState<KnowledgeEdge[]>([]);
    const [isProcessingAI, setIsProcessingAI] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [isOcrExpanded, setIsOcrExpanded] = useState(false);
    const [newTag, setNewTag] = useState('');
    const [pendingDeleteItemId, setPendingDeleteItemId] = useState<string | null>(null);
    const [versionHistory, setVersionHistory] = useState<KnowledgeVersionEntry[]>([]);
    const [detailTab, setDetailTab] = useState<'overview' | 'content' | 'history' | 'graph'>('overview');

    // Relational graph state (Fase 2B)
    const [edges, setEdges] = useState<KnowledgeEdge[]>([]);
    const [isAddingEdge, setIsAddingEdge] = useState(false);
    const [newEdgeTargetId, setNewEdgeTargetId] = useState('');
    const [newEdgeRelation, setNewEdgeRelation] = useState<RelationKind>('related_to');
    const [newEdgeValidFrom, setNewEdgeValidFrom] = useState('');
    const [newEdgeValidUntil, setNewEdgeValidUntil] = useState('');

    // Desktop UX State
    const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());
    const [contextMenu, setContextMenu] = useState<{ x: number, y: number, itemId: string | null } | null>(null);
    const [scrollTop, setScrollTop] = useState(0);
    const [isAddressEditing, setIsAddressEditing] = useState(false);
    const [addressInput, setAddressInput] = useState('');
    const [editOcrText, setEditOcrText] = useState<string | null>(null);
    const [clipboard, setClipboard] = useState<{ type: 'copy'|'cut', ids: string[] }>({ type: 'copy', ids: [] });
    const [renamingItemId, setRenamingItemId] = useState<string | null>(null);
    const [renamingSidebarFolderId, setRenamingSidebarFolderId] = useState<string | null>(null);
    const [sidebarRenameValue, setSidebarRenameValue] = useState('');
    const [lassoStart, setLassoStart] = useState<{ x: number, y: number } | null>(null);
    const [lassoCurrent, setLassoCurrent] = useState<{ x: number, y: number } | null>(null);
    const [undoStackLocal, setUndoStackLocal] = useState<{action: string, data: any}[]>([]);
    const lassoBaseSelectionRef = useRef<Set<string>>(new Set());
    const lassoIsAdditiveRef = useRef(false);
    const [expandedFolderIds, setExpandedFolderIds] = useState<Set<string>>(
        new Set([ROOT_ACTIONS_FOLDER_ID, ROOT_HEALTH_FOLDER_ID, ROOT_PROJECTS_FOLDER_ID])
    );

    // Virtual Scrolling Variables
    const [activeBaseId, setActiveBaseId] = useState<string | null>(null);

    // Virtual Scrolling Variables
    const [containerWidth, setContainerWidth] = useState(1000);
    const gridCols = containerWidth < 768 ? 2 : containerWidth < 1024 ? 4 : containerWidth < 1280 ? 5 : 6;
    const itemHeightGrid = 160;
    const itemHeightList = 64;
    const listSizeColWidth = 96;
    const listModifiedColWidth = 210;
    const listActionsColWidth = 92;

    // Modals State
    const [isLinkModalOpen, setIsLinkModalOpen] = useState(false);
    const [linkUrl, setLinkUrl] = useState('');
    const [linkTitle, setLinkTitle] = useState('');
    const [isNewFolderModalOpen, setIsNewFolderModalOpen] = useState(false);
    const [newFolderName, setNewFolderName] = useState('');

    const currentItem = useMemo(() => {
        if (!selectedItem) return null;
        return items.find(i => i.id === selectedItem.id) || selectedItem;
    }, [items, selectedItem]);

    useEffect(() => {
        let cancelled = false;
        const loadHistory = async () => {
            if (!currentItem || currentItem.is_folder) {
                setVersionHistory([]);
                return;
            }
            try {
                const historyQuery = query(
                    collection(db, 'conhecimento', currentItem.id, 'history'),
                    orderBy('captured_at', 'desc'),
                    limit(6)
                );
                const snapshot = await getDocs(historyQuery);
                if (cancelled) return;
                setVersionHistory(snapshot.docs.map(docSnap => ({
                    id: docSnap.id,
                    ...docSnap.data(),
                } as KnowledgeVersionEntry)));
            } catch (error) {
                console.error('Erro ao carregar histórico do conhecimento:', error);
                if (!cancelled) setVersionHistory([]);
            }
        };
        loadHistory();
        return () => { cancelled = true; };
    }, [currentItem]);

    useEffect(() => {
        setDetailTab('overview');
        setIsOcrExpanded(false);
        setEditOcrText(null);
    }, [currentItem?.id]);

    useEffect(() => {
        let cancelled = false;
        if (!currentItem || currentItem.is_folder) { setEdges([]); return; }
        getEdgesForItem(db, currentItem.id).then(loaded => {
            if (!cancelled) setEdges(loaded);
        }).catch(() => {
            if (!cancelled) setEdges([]);
        });
        return () => { cancelled = true; };
    }, [currentItem]);

    useEffect(() => {
        let cancelled = false;
        if (!isGlobalGraphOpen) return;
        const loadAllEdges = async () => {
            try {
                const snapshot = await getDocs(collection(db, 'knowledge_edges'));
                if (!cancelled) {
                    setGlobalEdges(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as KnowledgeEdge)));
                }
            } catch (error) {
                console.error("Erro no Mapa Global:", error);
            }
        };
        loadAllEdges();
        return () => { cancelled = true; };
    }, [isGlobalGraphOpen]);

    const folderStructure = useMemo(() => {
        return computeFolderStructure(items, allTasks);
    }, [items, allTasks]);

    const breadcrumbs = useMemo(() => {
        const rootName = activeBaseId ? knowledgeBases.find(b => b.id === activeBaseId)?.nome || 'Base' : 'Biblioteca';
        const root: { id: string | null, name: string } = { id: null, name: rootName };
        if (!currentFolderId) return [root];

        const folderMap = new Map(folderStructure.map(folder => [folder.id, folder]));
        const chain: { id: string, name: string }[] = [];
        const visited = new Set<string>();
        let cursor: string | null = currentFolderId;

        while (cursor && !visited.has(cursor)) {
            visited.add(cursor);
            const folder = folderMap.get(cursor);
            if (!folder) break;
            chain.unshift({ id: folder.id, name: folder.titulo });
            cursor = folder.parent_id || null;
        }

        return [root, ...chain];
    }, [currentFolderId, folderStructure, activeBaseId, knowledgeBases]);

    const currentItems = useMemo(() => {
        return filterCurrentItems(items, allTasks, folderStructure, currentFolderId, searchTerm, searchMode, activeBaseId);
    }, [items, currentFolderId, searchTerm, searchMode, allTasks, folderStructure, activeBaseId]);

    const scopedKnowledgeStats = useMemo(() => {
        const docs = currentItems.filter(item => !item.is_folder);
        const folders = currentItems.filter(item => item.is_folder);
        const pending = docs.filter(isKnowledgeProcessingPending);
        const summarized = docs.filter(item => !!item.resumo_tldr);
        const mapped = docs.filter(item => !!item.memory_location);
        const linked = docs.filter(item => !!item.origem || !!item.base_id);
        return {
            docs: docs.length,
            folders: folders.length,
            pending: pending.length,
            summarized: summarized.length,
            mapped: mapped.length,
            linked: linked.length,
            pendingSamples: pending.slice(0, 3),
            recentSamples: docs
                .slice()
                .sort((a, b) => (b.data_atualizacao || b.data_criacao || '').localeCompare(a.data_atualizacao || a.data_criacao || ''))
                .slice(0, 3),
        };
    }, [currentItems]);

    const currentScopeLabel = useMemo(() => {
        if (activeTab === 'master') return 'Manual do Hermes';
        if (currentFolderId) return breadcrumbs[breadcrumbs.length - 1]?.name || 'Pasta';
        if (activeBaseId) return knowledgeBases.find(base => base.id === activeBaseId)?.nome || 'Base ativa';
        return 'Biblioteca operacional';
    }, [activeTab, currentFolderId, breadcrumbs, activeBaseId, knowledgeBases]);

    const isVirtualItem = (item: ConhecimentoItem) =>
        isRootKnowledgeFolderId(item.id) || isActionVirtualFolderId(item.id) || isActionDiaryItemId(item.id);

    const getDestinationPatch = (targetFolderId: string | null): Partial<ConhecimentoItem> => {
        if (!targetFolderId) return { parent_id: null };

        if (targetFolderId === ROOT_ACTIONS_FOLDER_ID) {
            return { parent_id: null, categoria: 'Ações' };
        }
        if (targetFolderId === ROOT_HEALTH_FOLDER_ID) {
            return { parent_id: null, categoria: 'Saúde' };
        }
        if (targetFolderId === ROOT_PROJECTS_FOLDER_ID) {
            return { parent_id: null, categoria: 'Projetos' };
        }

        const actionTaskId = getTaskIdFromActionFolderId(targetFolderId);
        if (actionTaskId) {
            return {
                parent_id: null,
                categoria: 'Ações',
                origem: { modulo: 'tarefas', id_origem: actionTaskId }
            };
        }

        return { parent_id: targetFolderId };
    };

    const folderById = useMemo(() => {
        return new Map(folderStructure.map(folder => [folder.id, folder]));
    }, [folderStructure]);

    const sidebarChildrenByParent = useMemo(() => {
        const map = new Map<string | null, ConhecimentoItem[]>();

        folderStructure.forEach((folder) => {
            const parentKey = folder.parent_id || null;
            const siblings = map.get(parentKey) || [];
            siblings.push(folder);
            map.set(parentKey, siblings);
        });

        map.forEach((siblings, parentId) => {
            if (parentId === null) {
                siblings.sort((a, b) => {
                    const rootOrder = [ROOT_ACTIONS_FOLDER_ID, ROOT_HEALTH_FOLDER_ID, ROOT_PROJECTS_FOLDER_ID];
                    const indexA = rootOrder.indexOf(a.id);
                    const indexB = rootOrder.indexOf(b.id);
                    if (indexA !== -1 || indexB !== -1) {
                        if (indexA === -1) return 1;
                        if (indexB === -1) return -1;
                        return indexA - indexB;
                    }
                    return a.titulo.localeCompare(b.titulo, 'pt-BR');
                });
            } else {
                siblings.sort((a, b) => a.titulo.localeCompare(b.titulo, 'pt-BR'));
            }
        });

        return map;
    }, [folderStructure]);

    const isFolderSearchActive = searchTerm.trim().length > 0 && searchMode !== 'files';

    const visibleSidebarFolderIds = useMemo(() => {
        if (!isFolderSearchActive) return null;

        const query = searchTerm.toLowerCase().trim();
        const visibleIds = new Set<string>();

        const matches = folderStructure.filter(folder => folder.titulo.toLowerCase().includes(query));

        const addAncestors = (folderId: string) => {
            let cursor: string | null = folderId;
            const visited = new Set<string>();
            while (cursor && !visited.has(cursor)) {
                visited.add(cursor);
                visibleIds.add(cursor);
                const parentId = folderById.get(cursor)?.parent_id || null;
                cursor = parentId;
            }
        };

        matches.forEach(folder => addAncestors(folder.id));
        return visibleIds;
    }, [isFolderSearchActive, searchTerm, folderStructure, folderById]);

    const isRenamableFolder = (item: ConhecimentoItem) => {
        if (!item.is_folder) return false;
        if (isRootKnowledgeFolderId(item.id)) return false;
        return true;
    };

    const findSelectedItemForRename = () => {
        if (selectedItems.size !== 1) return null;
        const selectedId = Array.from(selectedItems)[0];
        return currentItems.find(item => item.id === selectedId) || folderById.get(selectedId) || null;
    };

    const handleRenameEntity = async (item: ConhecimentoItem, rawTitle: string) => {
        const title = rawTitle.trim();
        if (!title || title === item.titulo) return;

        const actionTaskId = getTaskIdFromActionFolderId(item.id);
        if (actionTaskId) {
            if (!onRenameAction) {
                alert('Renomear ações não está disponível neste contexto.');
                return;
            }
            await onRenameAction(actionTaskId, title);
            return;
        }

        if (!onSaveItem) return;
        if (isActionDiaryItemId(item.id) || isRootKnowledgeFolderId(item.id)) return;
        await onSaveItem({ id: item.id, titulo: title });
    };

    const startItemRename = (item: ConhecimentoItem) => {
        if (!isRenamableFolder(item) && item.is_folder) return;
        if (isRootKnowledgeFolderId(item.id) || isActionDiaryItemId(item.id)) return;
        setRenamingItemId(item.id);
    };

    useEffect(() => {
        if (!currentFolderId) return;
        const toExpand: string[] = [];
        let cursor: string | null = currentFolderId;
        const visited = new Set<string>();

        while (cursor && !visited.has(cursor)) {
            visited.add(cursor);
            const folder = folderById.get(cursor);
            if (!folder) break;
            if (folder.parent_id) toExpand.push(folder.parent_id);
            cursor = folder.parent_id || null;
        }

        if (toExpand.length === 0) return;
        setExpandedFolderIds((prev) => {
            const next = new Set(prev);
            toExpand.forEach(id => next.add(id));
            return next;
        });
    }, [currentFolderId, folderById]);

    // Handle Desktop Keyboard Shortcuts
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            // Ignore if typing in an input or textarea
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

            if (e.key === 'F2') {
                e.preventDefault();
                const target = findSelectedItemForRename();
                if (target) {
                    startItemRename(target);
                }
            }

            if (e.key === 'Delete') {
                const persistedSelectedIds = Array.from(selectedItems).filter(id => items.some(item => item.id === id));
                if (persistedSelectedIds.length > 0) {
                    if (window.confirm(`Tem certeza que deseja deletar ${persistedSelectedIds.length} item(s)?`)) {
                        persistedSelectedIds.forEach(id => onDeleteItem(id));
                        setSelectedItems(new Set());
                    }
                } else if (selectedItem && !selectedItem.is_folder) {
                    if (window.confirm(`Tem certeza que deseja deletar ${selectedItem.titulo}?`)) {
                        onDeleteItem(selectedItem.id);
                        setSelectedItem(null);
                    }
                }
            }

            if (e.key === 'a' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                setSelectedItems(new Set(currentItems.map(i => i.id)));
            }

            if (e.key === 'c' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                if (selectedItems.size > 0) {
                    setClipboard({ type: 'copy', ids: Array.from(selectedItems) });
                    alert(`${selectedItems.size} item(s) copiado(s).`);
                }
            }

            if (e.key === 'x' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                if (selectedItems.size > 0) {
                    setClipboard({ type: 'cut', ids: Array.from(selectedItems) });
                    alert(`${selectedItems.size} item(s) recortado(s).`);
                }
            }

            if (e.key === 'v' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                if (clipboard.ids.length > 0 && onSaveItem) {
                    clipboard.ids.forEach(id => {
                        const original = items.find(i => i.id === id);
                        if (original) {
                            if (clipboard.type === 'copy') {
                                // Duplicate
                                const newId = `copy_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
                                const copy = { ...original, id: newId, titulo: `${original.titulo} (Cópia)`, ...getDestinationPatch(currentFolderId) };
                                onSaveItem(copy);
                                setUndoStackLocal(prev => [...prev, { action: 'copy', data: newId }]);
                            } else {
                                // Move (Cut)
                                onSaveItem({ id: id, ...getDestinationPatch(currentFolderId) });
                                setUndoStackLocal(prev => [...prev, { action: 'move', data: { id, oldParent: original.parent_id } }]);
                            }
                        }
                    });
                    if (clipboard.type === 'cut') setClipboard({ type: 'copy', ids: [] });
                }
            }

            if (e.key === 'z' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                if (undoStackLocal.length > 0) {
                    const lastAction = undoStackLocal[undoStackLocal.length - 1];
                    if (lastAction.action === 'copy') {
                        onDeleteItem(lastAction.data);
                    } else if (lastAction.action === 'move' && onSaveItem) {
                        onSaveItem({ id: lastAction.data.id, parent_id: lastAction.data.oldParent });
                    }
                    setUndoStackLocal(prev => prev.slice(0, -1));
                }
            }

            if (e.key === 'Escape') {
                setSelectedItems(new Set());
                setContextMenu(null);
                setRenamingItemId(null);
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedItem, selectedItems, currentItems, onDeleteItem, clipboard, items, currentFolderId, onSaveItem, undoStackLocal, folderById]);

    const handleItemClick = (e: React.MouseEvent, item: ConhecimentoItem) => {
        e.stopPropagation();
        setContextMenu(null);

        if (e.ctrlKey || e.metaKey) {
            const newSelected = new Set(selectedItems);
            if (newSelected.has(item.id)) {
                newSelected.delete(item.id);
            } else {
                newSelected.add(item.id);
            }
            setSelectedItems(newSelected);
        } else if (e.shiftKey && selectedItems.size > 0) {
            // Basic range selection (first to current)
            const itemsArray = currentItems.map(i => i.id);
            const lastSelected = Array.from(selectedItems).pop()!;
            const startIdx = itemsArray.indexOf(lastSelected);
            const endIdx = itemsArray.indexOf(item.id);

            if (startIdx !== -1 && endIdx !== -1) {
                const [min, max] = [Math.min(startIdx, endIdx), Math.max(startIdx, endIdx)];
                const newSelected = new Set(selectedItems);
                for (let i = min; i <= max; i++) {
                    newSelected.add(itemsArray[i]);
                }
                setSelectedItems(newSelected);
            }
        } else {
            if (item.is_folder) {
                setCurrentFolderId(item.id);
                setSelectedItems(new Set());
            } else {
                setSelectedItem(item);
                setSelectedItems(new Set([item.id]));
            }
        }
    };

    const handleContextMenu = (e: React.MouseEvent, item: ConhecimentoItem) => {
        e.preventDefault();
        e.stopPropagation();
        if (isVirtualItem(item)) return;
        if (!selectedItems.has(item.id)) {
            setSelectedItems(new Set([item.id]));
        }
        setContextMenu({ x: e.clientX, y: e.clientY, itemId: item.id });
    };

    const handleAddEdge = async () => {
        if (!currentItem || !newEdgeTargetId) return;
        const edge: Omit<KnowledgeEdge, 'id'> = {
            source_id: currentItem.id,
            target_id: newEdgeTargetId,
            relation_kind: newEdgeRelation,
            created_at: new Date().toISOString(),
            created_by: 'user',
            ...(newEdgeValidFrom ? { valid_from: newEdgeValidFrom } : {}),
            ...(newEdgeValidUntil ? { valid_until: newEdgeValidUntil } : {}),
        };
        const id = await addEdge(db, edge);
        setEdges(prev => [{ ...edge, id }, ...prev]);
        setIsAddingEdge(false);
        setNewEdgeTargetId('');
        setNewEdgeRelation('related_to');
        setNewEdgeValidFrom('');
        setNewEdgeValidUntil('');
    };

    const handleRemoveEdge = async (edgeId: string) => {
        await removeEdge(db, edgeId);
        setEdges(prev => prev.filter(e => e.id !== edgeId));
    };

    const handleCopyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text);
        alert("Texto copiado para a área de transferência!");
    };

    const handleProcessCurrentItemWithAI = async () => {
        if (!currentItem || !onProcessWithAI) return;
        setIsProcessingAI(true);
        try {
            await onProcessWithAI(currentItem.id);
            alert('Processamento com IA solicitado.');
        } catch (error) {
            console.error('Erro ao processar item com IA:', error);
            alert('Falha ao processar item com IA.');
        } finally {
            setIsProcessingAI(false);
        }
    };

    const handleGenerateCurrentSlides = async () => {
        if (!currentItem || !onGenerateSlides) return;
        const sourceText = currentItem.resumo_tldr || currentItem.texto_bruto || '';
        if (!sourceText.trim()) {
            alert('Este item ainda não possui conteúdo suficiente para slides.');
            return;
        }
        try {
            const slides = await onGenerateSlides(sourceText);
            if (onSaveItem) {
                await onSaveItem({ id: currentItem.id, slides_data: slides });
            }
            alert('Slides gerados e vinculados ao item.');
        } catch (error) {
            console.error('Erro ao gerar slides:', error);
            alert('Falha ao gerar slides.');
        }
    };

    const handleCreateFolder = async () => {
        if (!newFolderName.trim() || !onSaveItem) return;
        // Mock ID creation, usually handled by backend but onSaveItem implies partial update?
        // Wait, onSaveItem is for updating existing? Usually yes.
        // But the previous code didn't have create function passed.
        // Assuming I need to hack it via onSaveItem or if onUploadFile can be repurposed?
        // Actually, I should use a new method but I can't change props easily without changing parent.
        // Wait, app logic usually has `addDoc`. The parent `App` component defines these handlers.
        // I will assume `onSaveItem` with NO ID creates a new item if implemented that way, OR I should have `onAddItem`.
        // Looking at `index.tsx`, `onSaveItem` calls `handleSaveKnowledgeItem` which likely updates.
        // I might need to abuse `onUploadFile` or `onAddLink`.
        // Actually, `onAddLink` creates a new item with type 'link'.
        // I will use `onSaveItem` but with a new ID generated here, hoping it works, or I'll use `onAddLink` and hack it?
        // No, `onAddLink` takes url and title.
        // Let's check `App` component again. `onSaveItem` does `updateDoc` or `setDoc`?
        // In `index.tsx`: `onSaveItem={handleSaveKnowledgeItem}`.
        // Let's check `handleSaveKnowledgeItem`.

        /*
        const handleSaveKnowledgeItem = async (item: Partial<ConhecimentoItem>) => {
            if (item.id) {
                await updateDoc(doc(db, 'conhecimento', item.id), item);
                showToast("Item atualizado!", "success");
            }
        };
        */

        // It only updates. I need to create.
        // I will add a new prop `onCreateFolder` or reuse `onAddLink` if I can't change `App`.
        // But I CAN change `App`. I am supposed to "Transform the Knowledge module".
        // I will add `onCreateFolder` to `KnowledgeViewProps` and `App` later.
        // For now I will assume it exists or I will verify `index.tsx` logic.
        // Wait, I can't modify `index.tsx` in this step. I am modifying `KnowledgeView.tsx`.
        // I will add the prop to the interface now, and update `index.tsx` in a later step.
        // Actually, I can use `onSaveItem` if I modify `index.tsx` to handle creation if ID is missing or if I generate ID here.
        // `setDoc` allows specifying ID.
    };

    const getFileIcon = (item: ConhecimentoItem) => {
        if (item.is_folder) return (
            <svg className="w-10 h-10 text-amber-400" fill="currentColor" viewBox="0 0 24 24"><path d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" /></svg>
        );
        const t = item.tipo_arquivo.toLowerCase();
        if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(t)) return (
            <svg className="w-10 h-10 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
        );
        if (t === 'pdf') return (
            <svg className="w-10 h-10 text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 9h1m0 4h1m0 4h1" /></svg>
        );
        if (['mp4', 'mov', 'avi', 'webm', 'mkv'].includes(t)) return (
            <svg className="w-10 h-10 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
        );
        if (['mp3', 'wav', 'm4a', 'ogg'].includes(t)) return (
            <svg className="w-10 h-10 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
        );
        if (['doc', 'docx', 'txt', 'rtf'].includes(t)) return (
            <svg className="w-10 h-10 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
        );
        return (
            <svg className="w-10 h-10 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.707.293V19a2 2 0 01-2 2z" /></svg>
        );
    };

    const handleDrop = (e: React.DragEvent, targetFolderId: string | null) => {
        e.preventDefault();
        const itemId = e.dataTransfer.getData("text/plain");
        if (itemId && onSaveItem) {
            if (itemId === targetFolderId) return; // Can't move folder into itself (simple check)
            onSaveItem({ id: itemId, ...getDestinationPatch(targetFolderId) });
        }
    };

    const formatSize = (bytes: number) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    };

    const handleLocalSync = async () => {
        try {
            if (!('showDirectoryPicker' in window)) {
                alert('A File System Access API não é suportada no seu navegador.');
                return;
            }

            const directoryHandle = await (window as any).showDirectoryPicker({
                mode: 'readwrite'
            });

            if (!onSaveItem) return;

            // Simple shallow sync for demonstration purposes
            for await (const entry of directoryHandle.values()) {
                if (entry.kind === 'file') {
                    const fileHandle = entry as any;
                    const file = await fileHandle.getFile();

                    // Create a virtual local item
                    // Check if we already have it to avoid duplicates? Simple implementation generates new IDs
                    const newId = `local_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                    const ext = file.name.split('.').pop()?.toLowerCase() || 'txt';
                    let type = 'doc';
                    if (['pdf'].includes(ext)) type = 'pdf';
                    if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) type = 'imagem';
                    if (['mp4', 'mov', 'avi', 'webm', 'mkv'].includes(ext)) type = 'video';
                    if (['mp3', 'wav', 'm4a', 'ogg'].includes(ext)) type = 'audio';

                    // Read text content if it's a doc to populate texto_bruto for editing
                    let textContent = '';
                    if (type === 'doc') {
                        try {
                            textContent = await file.text();
                        } catch (e) {
                            console.error("Failed to read text from file", e);
                        }
                    }

                    // Save the file handle to IndexedDB instead of passing it to Firestore via onSaveItem
                    await idb.set(`fileHandle_${newId}`, fileHandle);

                    await onSaveItem({
                        id: newId,
                        titulo: file.name,
                        tipo_arquivo: type,
                        url_drive: URL.createObjectURL(file), // blob url for local preview
                        tamanho: file.size,
                        data_criacao: new Date(file.lastModified).toISOString(),
                        is_folder: false,
                        parent_id: currentFolderId,
                        texto_bruto: textContent,
                        fileHandle: true // Just a boolean flag for the UI to know it's a local file
                    });
                }
            }
        } catch (error) {
            console.error('Error syncing local directory:', error);
        }
    };

    const getIntersectingItemIds = (
        container: HTMLDivElement,
        lassoRect: { left: number; right: number; top: number; bottom: number }
    ) => {
        const ids = new Set<string>();
        const containerRect = container.getBoundingClientRect();
        const itemElements = container.querySelectorAll<HTMLElement>('[data-knowledge-item-id]');

        itemElements.forEach((element) => {
            const id = element.dataset.knowledgeItemId;
            if (!id) return;

            const rect = element.getBoundingClientRect();
            const itemRect = {
                left: rect.left - containerRect.left + container.scrollLeft,
                right: rect.right - containerRect.left + container.scrollLeft,
                top: rect.top - containerRect.top + container.scrollTop,
                bottom: rect.bottom - containerRect.top + container.scrollTop
            };

            const intersects =
                itemRect.left < lassoRect.right &&
                itemRect.right > lassoRect.left &&
                itemRect.top < lassoRect.bottom &&
                itemRect.bottom > lassoRect.top;

            if (intersects) ids.add(id);
        });

        return ids;
    };

    const toggleFolderExpanded = (folderId: string) => {
        setExpandedFolderIds((prev) => {
            const next = new Set(prev);
            if (next.has(folderId)) next.delete(folderId);
            else next.add(folderId);
            return next;
        });
    };

    const submitSidebarFolderRename = async (folder: ConhecimentoItem) => {
        try {
            await handleRenameEntity(folder, sidebarRenameValue);
        } catch (error) {
            console.error('Erro ao renomear pasta:', error);
            alert('Não foi possível renomear a pasta.');
        } finally {
            setRenamingSidebarFolderId(null);
            setSidebarRenameValue('');
        }
    };

    const renderSidebarFolder = (folder: ConhecimentoItem, depth: number) => {
        const children = (sidebarChildrenByParent.get(folder.id) || []).filter(
            child => !visibleSidebarFolderIds || visibleSidebarFolderIds.has(child.id)
        );
        const hasChildren = children.length > 0;
        const isExpanded = isFolderSearchActive ? true : expandedFolderIds.has(folder.id);
        const isSelected = currentFolderId === folder.id;
        const canRename = isRenamableFolder(folder);

        return (
            <div key={folder.id}>
                <div
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => handleDrop(e, folder.id)}
                    style={{ marginLeft: `${depth * 12}px` }}
                    className={`group w-full flex items-center gap-2 px-3 py-2 rounded-xl transition-all mb-1 ${isSelected ? 'bg-slate-100 text-slate-900 font-bold' : 'text-slate-500 hover:bg-slate-50'}`}
                >
                    <button
                        type="button"
                        onClick={() => hasChildren ? toggleFolderExpanded(folder.id) : setCurrentFolderId(folder.id)}
                        className={`w-4 h-4 shrink-0 flex items-center justify-center ${hasChildren ? 'text-slate-400 hover:text-slate-700' : 'opacity-0 pointer-events-none'}`}
                        aria-label={hasChildren ? (isExpanded ? 'Recolher pasta' : 'Expandir pasta') : 'Sem subpastas'}
                    >
                        {hasChildren && (
                            <svg className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
                            </svg>
                        )}
                    </button>

                    <button
                        type="button"
                        onClick={() => setCurrentFolderId(folder.id)}
                        className="flex-1 min-w-0 flex items-center gap-2 text-left"
                        title={folder.titulo}
                    >
                        <span className="w-4 h-4 min-w-[16px] shrink-0 flex items-center justify-center text-amber-400">
                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                                <path d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
                            </svg>
                        </span>
                        {renamingSidebarFolderId === folder.id ? (
                            <input
                                autoFocus
                                value={sidebarRenameValue}
                                onChange={(e) => setSidebarRenameValue(e.target.value)}
                                onBlur={() => submitSidebarFolderRename(folder)}
                                onClick={(e) => e.stopPropagation()}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') e.currentTarget.blur();
                                    if (e.key === 'Escape') {
                                        setRenamingSidebarFolderId(null);
                                        setSidebarRenameValue('');
                                    }
                                }}
                                className="w-full bg-white border border-blue-300 rounded px-2 py-0.5 text-[11px] font-semibold text-slate-800 outline-none"
                            />
                        ) : (
                            <span className="text-[11px] truncate">{folder.titulo}</span>
                        )}
                    </button>

                    {canRename && renamingSidebarFolderId !== folder.id && (
                        <button
                            type="button"
                            onClick={() => {
                                setRenamingSidebarFolderId(folder.id);
                                setSidebarRenameValue(folder.titulo);
                            }}
                            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 text-slate-400 hover:text-blue-600"
                            title="Renomear pasta"
                        >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                            </svg>
                        </button>
                    )}
                </div>

                {hasChildren && isExpanded && children.map(child => renderSidebarFolder(child, depth + 1))}
            </div>
        );
    };

    return (
        <div className="flex min-h-[calc(100vh-88px)] bg-slate-50 overflow-hidden animate-in fade-in duration-500">
            {/* Sidebar - Folder Tree */}
            <aside className="hidden md:flex w-72 bg-white border-r border-slate-100 flex-col">
                <div className="p-8 border-b border-slate-50">
                    <h3 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] mb-1">Explorer</h3>
                    <p className="text-[9px] text-slate-400 font-bold uppercase">Arquivos & Pastas</p>
                </div>

                <nav className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                    <button
                        onClick={() => {
                            setCurrentFolderId(null);
                            setActiveTab('library');
                        }}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => handleDrop(e, null)}
                        className={`w-full flex items-center gap-3 px-4 py-2 rounded-xl transition-all mb-1 ${currentFolderId === null && activeTab === 'library' ? 'bg-slate-100 text-slate-900 font-bold' : 'text-slate-500 hover:bg-slate-50'}`}
                    >
                        <svg className="w-4 h-4 text-amber-400" fill="currentColor" viewBox="0 0 24 24"><path d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" /></svg>
                        <span className="text-[11px]">Biblioteca</span>
                    </button>

                    <button
                        onClick={() => setActiveTab('master')}
                        className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all mb-4 ${activeTab === 'master' ? 'bg-violet-600 text-white font-bold shadow-lg shadow-violet-200' : 'text-slate-500 hover:bg-slate-50'}`}
                    >
                        <div className={`w-5 h-5 rounded-lg flex items-center justify-center ${activeTab === 'master' ? 'bg-white/20' : 'bg-violet-100 text-violet-600'}`}>
                           <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                        </div>
                        <span className="text-[11px]">Manual do HERMES</span>
                        {masterKnowledge.length > 0 && (
                            <span className="ml-auto bg-violet-400 text-white text-[8px] px-1.5 py-0.5 rounded-full">{masterKnowledge.length}</span>
                        )}
                    </button>

                    <div className="px-4 py-2">
                        <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Bases RAG</h4>
                    </div>

                    {knowledgeBases.map(base => (
                        <button
                            key={base.id}
                            onClick={() => {
                                setActiveBaseId(base.id);
                                setActiveTab('library');
                                setCurrentFolderId(null);
                            }}
                            className={`w-full flex items-center gap-3 px-4 py-2 rounded-xl transition-all mb-1 ${activeBaseId === base.id ? 'bg-blue-100 text-blue-800 font-bold' : 'text-slate-500 hover:bg-slate-50'}`}
                        >
                            <span style={{ color: base.cor || '#64748b' }}>{base.emoji || '🗂️'}</span>
                            <span className="text-[11px] truncate">{base.nome}</span>
                            {base.contagem_elementos && base.contagem_elementos > 0 ? (
                                <span className="ml-auto bg-slate-200 text-slate-600 text-[8px] font-black px-1.5 py-0.5 rounded-full">{base.contagem_elementos}</span>
                            ) : null}
                        </button>
                    ))}
                    
                    <button
                        onClick={() => {
                            const newName = prompt('Nome da nova Base de Conhecimento:');
                            if (newName) onCreateBase(newName);
                        }}
                        className="w-full flex items-center gap-3 px-4 py-2 rounded-xl transition-all text-slate-400 hover:text-blue-600 hover:bg-blue-50"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                        <span className="text-[11px] font-bold">Nova Base RAG</span>
                    </button>

                    <div className="h-px bg-slate-100 my-4"></div>

                    {activeTab === 'library' && !activeBaseId && (sidebarChildrenByParent.get(null) || [])
                        .filter(folder => !visibleSidebarFolderIds || visibleSidebarFolderIds.has(folder.id))
                        .map(folder => renderSidebarFolder(folder, 0))}
                    
                    {activeTab === 'library' && activeBaseId && (sidebarChildrenByParent.get(null) || [])
                        .filter(folder => folder.base_id === activeBaseId)
                        .filter(folder => !visibleSidebarFolderIds || visibleSidebarFolderIds.has(folder.id))
                        .map(folder => renderSidebarFolder(folder, 0))}
                </nav>

                <div className="p-6 border-t border-slate-50 space-y-3">
                    <button
                        onClick={handleLocalSync}
                        className="w-full bg-slate-100 hover:bg-slate-200 text-slate-600 px-6 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-3"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                        Sincronizar Pasta
                    </button>
                    <button
                        onClick={() => setIsNewFolderModalOpen(true)}
                        className="w-full bg-slate-100 hover:bg-slate-200 text-slate-600 px-6 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-3"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                        Nova Pasta
                    </button>
                    <label className="w-full bg-slate-900 text-white hover:bg-slate-800 px-6 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all cursor-pointer flex items-center justify-center gap-3 shadow-lg">
                        <input
                            type="file"
                            className="hidden"
                            ref={fileInputRef}
                            onChange={async (e) => {
                                const file = e.target.files?.[0];
                                if (file) {
                                    setIsUploading(true);
                                    try {
                                        await onUploadFile(file, currentFolderId, activeBaseId);
                                    } finally {
                                        setIsUploading(false);
                                        if (fileInputRef.current) fileInputRef.current.value = '';
                                    }
                                }
                            }}
                        />
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                        Upload Arquivo
                    </label>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col min-w-0 bg-slate-50">
                {/* Search Header */}
                <header className="p-8 bg-white border-b border-slate-100 flex items-center justify-between gap-8">
                    {/* Breadcrumbs / Address Bar */}
                    <div className="flex-1 flex items-center gap-2 overflow-x-auto no-scrollbar" onDoubleClick={() => {
                        setIsAddressEditing(true);
                        setAddressInput(breadcrumbs.map(c => c.name).join('/'));
                    }}>
                        {isAddressEditing ? (
                            <input
                                autoFocus
                                type="text"
                                className="w-full text-sm font-medium text-slate-900 bg-slate-50 border border-blue-200 rounded-lg px-3 py-1.5 outline-none focus:ring-2 focus:ring-blue-500"
                                value={addressInput}
                                onChange={(e) => setAddressInput(e.target.value)}
                                onBlur={() => setIsAddressEditing(false)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                        const parts = addressInput.split('/').map(p => p.trim());
                                        const targetName = parts[parts.length - 1];
                                        const targetFolder = folderStructure.find(f => f.titulo === targetName);
                                        if (targetFolder) {
                                            setCurrentFolderId(targetFolder.id);
                                        } else if (['raiz', 'biblioteca'].includes(targetName.toLowerCase())) {
                                            setCurrentFolderId(null);
                                        }
                                        setIsAddressEditing(false);
                                    }
                                    if (e.key === 'Escape') setIsAddressEditing(false);
                                }}
                            />
                        ) : (
                            breadcrumbs.map((crumb, idx) => (
                                <React.Fragment key={crumb.id || 'root'}>
                                    {idx > 0 && <span className="text-slate-300">/</span>}
                                    <button
                                        onClick={() => setCurrentFolderId(crumb.id)}
                                        className={`text-sm whitespace-nowrap ${idx === breadcrumbs.length - 1 ? 'font-black text-slate-900' : 'font-medium text-slate-500 hover:text-blue-600'}`}
                                    >
                                        {crumb.name}
                                    </button>
                                </React.Fragment>
                            ))
                        )}
                    </div>

                    {selectedItems.size > 0 ? (
                        <div className="flex-1 flex items-center justify-end gap-3 animate-in fade-in duration-200">
                            <span className="text-xs font-bold text-slate-500 mr-2">{selectedItems.size} selecionado(s)</span>
                            {selectedItems.size === 1 && (
                                <button
                                    onClick={() => {
                                        const item = items.find(i => i.id === Array.from(selectedItems)[0]);
                                        if (item && !item.is_folder) {
                                            setSelectedItem(item);
                                        } else if (item && item.is_folder && !isVirtualItem(item)) {
                                            startItemRename(item);
                                        }
                                    }}
                                    className="p-2 bg-blue-50 text-blue-600 hover:bg-blue-100 rounded-lg text-[10px] font-black uppercase tracking-widest transition-colors flex items-center gap-2"
                                >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                    Editar
                                </button>
                            )}
                            <button
                                onClick={() => {
                                    setMoveTargetFolderId(currentFolderId);
                                    setIsMoveModalOpen(true);
                                }}
                                className="p-2 bg-purple-50 text-purple-600 hover:bg-purple-100 rounded-lg text-[10px] font-black uppercase tracking-widest transition-colors flex items-center gap-2"
                            >
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 5l7 7-7 7M5 5l7 7-7 7" /></svg>
                                Mover
                            </button>
                            <button
                                onClick={() => {
                                    const persistedSelectedIds = Array.from(selectedItems).filter(id => items.some(item => item.id === id));
                                    if (window.confirm(`Tem certeza que deseja deletar ${persistedSelectedIds.length} item(s)?`)) {
                                        persistedSelectedIds.forEach(id => onDeleteItem(id));
                                        setSelectedItems(new Set());
                                    }
                                }}
                                className="p-2 bg-rose-50 text-rose-600 hover:bg-rose-100 rounded-lg text-[10px] font-black uppercase tracking-widest transition-colors flex items-center gap-2"
                            >
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                Excluir
                            </button>
                            <button
                                onClick={() => setSelectedItems(new Set())}
                                className="p-2 text-slate-400 hover:text-slate-600 rounded-lg transition-colors ml-2"
                                title="Limpar Seleção"
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </div>
                    ) : (
                    <div className="flex-1 max-w-xl flex items-center gap-3">
                        <div className="flex-1 relative">
                            <svg className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                            <input
                                type="text"
                                placeholder={searchMode === 'folders' ? 'Buscar pastas...' : searchMode === 'files' ? 'Buscar arquivos...' : 'Buscar pastas e arquivos...'}
                                value={searchTerm}
                                onChange={(e) => {
                                    setSearchTerm(e.target.value);
                                    if (e.target.value && activeTab !== 'library') setActiveTab('library');
                                }}
                                className="w-full bg-slate-50 border-none rounded-xl pl-10 pr-4 py-3 text-xs font-bold text-slate-700 focus:ring-2 focus:ring-blue-500 transition-all outline-none"
                            />
                        </div>

                        <div className="flex bg-slate-100 p-1 rounded-xl shrink-0">
                            <button
                                onClick={() => setSearchMode('all')}
                                className={`px-2.5 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${searchMode === 'all' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                            >
                                Tudo
                            </button>
                            <button
                                onClick={() => setSearchMode('folders')}
                                className={`px-2.5 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${searchMode === 'folders' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                            >
                                Pastas
                            </button>
                            <button
                                onClick={() => setSearchMode('files')}
                                className={`px-2.5 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${searchMode === 'files' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                            >
                                Arquivos
                            </button>
                        </div>
                    </div>
                    )}

                    <div className="flex bg-slate-100 p-1 rounded-xl">
                        <button
                            onClick={() => setViewMode('grid')}
                            className={`p-2 rounded-lg transition-all ${viewMode === 'grid' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6z" /></svg>
                        </button>
                        <button
                            onClick={() => setViewMode('list')}
                            className={`p-2 rounded-lg transition-all ${viewMode === 'list' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" /></svg>
                        </button>
                    </div>
                </header>

                {activeTab === 'library' && (
                    <section className="px-8 pt-6 pb-2 bg-slate-50 border-b border-slate-100/70">
                        <div className="bg-white border border-slate-200 rounded-[2rem] p-6 shadow-sm">
                            <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
                                <div className="space-y-3">
                                    <div className="flex items-center gap-3 flex-wrap">
                                        <span className="px-3 py-1 rounded-full bg-slate-900 text-white text-[10px] font-black uppercase tracking-[0.2em]">
                                            Memória Operacional
                                        </span>
                                        <span className="px-3 py-1 rounded-full bg-blue-50 text-blue-700 text-[10px] font-black uppercase tracking-[0.2em]">
                                            {currentScopeLabel}
                                        </span>
                                        {activeBaseId && (
                                            <span className="px-3 py-1 rounded-full bg-violet-50 text-violet-700 text-[10px] font-black uppercase tracking-[0.2em]">
                                                Base ativa
                                            </span>
                                        )}
                                    </div>
                                    <div>
                                        <h2 className="text-2xl md:text-3xl font-black text-slate-900 tracking-tight">
                                            Conhecimento com contexto, proveniência e ação
                                        </h2>
                                        <p className="text-sm text-slate-500 font-medium max-w-3xl mt-2">
                                            Este espaço agora prioriza o que está pronto para uso operacional: documentos com contexto, itens que ainda precisam de IA e memória já posicionada no MemPalace.
                                        </p>
                                    </div>
                                </div>

                                <div className="flex flex-wrap gap-3">
                                    <button
                                        onClick={() => setIsGlobalGraphOpen(v => !v)}
                                        className={`px-4 py-3 rounded-2xl text-[10px] font-black uppercase tracking-[0.2em] transition-all flex items-center gap-2 ${isGlobalGraphOpen ? 'bg-violet-600 text-white shadow-violet-200 shadow-xl' : 'bg-violet-50 hover:bg-violet-100 text-violet-700'}`}
                                    >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                        {isGlobalGraphOpen ? 'Sair do Mapa' : 'Mapa Mental'}
                                    </button>
                                    <button
                                        onClick={() => setIsNewFolderModalOpen(true)}
                                        className="px-4 py-3 rounded-2xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-[10px] font-black uppercase tracking-[0.2em] transition-all"
                                    >
                                        Nova pasta
                                    </button>
                                    <button
                                        onClick={() => setIsLinkModalOpen(true)}
                                        className="px-4 py-3 rounded-2xl bg-blue-50 hover:bg-blue-100 text-blue-700 text-[10px] font-black uppercase tracking-[0.2em] transition-all"
                                    >
                                        Novo link
                                    </button>
                                    <button
                                        onClick={() => fileInputRef.current?.click()}
                                        className="px-4 py-3 rounded-2xl bg-slate-900 hover:bg-slate-800 text-white text-[10px] font-black uppercase tracking-[0.2em] transition-all shadow-lg"
                                    >
                                        {isUploading ? 'Enviando...' : 'Adicionar arquivo'}
                                    </button>
                                </div>
                            </div>

                            {isGlobalGraphOpen ? (
                                <div className="mt-8 h-[700px]">
                                    <GlobalKnowledgeGraph 
                                        items={items.filter(i => !i.is_folder)} 
                                        edges={globalEdges} 
                                        onNodeClick={(id) => {
                                            const item = items.find(i => i.id === id);
                                            if (item) {
                                                setSelectedItem(item);
                                                setIsGlobalGraphOpen(false);
                                            }
                                        }}
                                    />
                                </div>
                            ) : (
                                <>
                                    <div className="grid grid-cols-2 xl:grid-cols-6 gap-3 mt-6">
                                        {[
                                            { label: 'Documentos', value: scopedKnowledgeStats.docs, tone: 'bg-slate-50 text-slate-900 border-slate-200' },
                                            { label: 'Pastas', value: scopedKnowledgeStats.folders, tone: 'bg-amber-50 text-amber-800 border-amber-200' },
                                            { label: 'Pendentes IA', value: scopedKnowledgeStats.pending, tone: 'bg-rose-50 text-rose-700 border-rose-200' },
                                            { label: 'Com resumo', value: scopedKnowledgeStats.summarized, tone: 'bg-blue-50 text-blue-700 border-blue-200' },
                                            { label: 'No MemPalace', value: scopedKnowledgeStats.mapped, tone: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
                                            { label: 'Contextualizados', value: scopedKnowledgeStats.linked, tone: 'bg-violet-50 text-violet-700 border-violet-200' },
                                        ].map((stat) => (
                                            <div key={stat.label} className={`rounded-2xl border p-4 ${stat.tone}`}>
                                                <p className="text-[10px] font-black uppercase tracking-[0.2em] opacity-80">{stat.label}</p>
                                                <p className="text-2xl font-black mt-2">{stat.value}</p>
                                            </div>
                                        ))}
                                    </div>

                                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-6">
                                        <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50/70 p-4">
                                            <div className="flex items-center justify-between gap-3 mb-3">
                                                <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-500">Fila operacional</h3>
                                                <span className="text-[10px] font-bold text-slate-400 uppercase">{scopedKnowledgeStats.pendingSamples.length} amostras</span>
                                            </div>
                                            {scopedKnowledgeStats.pendingSamples.length === 0 ? (
                                                <p className="text-sm text-slate-400 font-medium">Nenhum item pendente de processamento neste escopo.</p>
                                            ) : (
                                                <div className="space-y-2">
                                                    {scopedKnowledgeStats.pendingSamples.map(item => (
                                                        <button
                                                            key={item.id}
                                                            onClick={() => setSelectedItem(item)}
                                                            className="w-full text-left bg-white rounded-2xl border border-slate-200 p-3 hover:border-blue-300 hover:shadow-sm transition-all"
                                                        >
                                                            <div className="flex items-start justify-between gap-3">
                                                                <div className="min-w-0">
                                                                    <p className="text-sm font-bold text-slate-900 truncate">{item.titulo}</p>
                                                                    <p className="text-[11px] text-slate-500 mt-1 line-clamp-2">{item.resumo_tldr || item.texto_bruto || 'Sem resumo ainda'}</p>
                                                                </div>
                                                                <span className={`shrink-0 px-2 py-1 rounded-full text-[9px] font-black uppercase tracking-widest ${getProcessingTone(item)}`}>
                                                                    {getProcessingLabel(item)}
                                                                </span>
                                                            </div>
                                                        </button>
                                                    ))}
                                                </div>
                                            )}
                                        </div>

                                        <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50/70 p-4">
                                            <div className="flex items-center justify-between gap-3 mb-3">
                                                <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-500">Atualizações recentes</h3>
                                                <span className="text-[10px] font-bold text-slate-400 uppercase">Memória viva</span>
                                            </div>
                                            {scopedKnowledgeStats.recentSamples.length === 0 ? (
                                                <p className="text-sm text-slate-400 font-medium">Nenhum item recente neste escopo.</p>
                                            ) : (
                                                <div className="space-y-2">
                                                    {scopedKnowledgeStats.recentSamples.map(item => (
                                                        <button
                                                            key={item.id}
                                                            onClick={() => setSelectedItem(item)}
                                                            className="w-full text-left bg-white rounded-2xl border border-slate-200 p-3 hover:border-violet-300 hover:shadow-sm transition-all"
                                                        >
                                                            <div className="flex items-center justify-between gap-3">
                                                                <div className="min-w-0">
                                                                    <p className="text-sm font-bold text-slate-900 truncate">{item.titulo}</p>
                                                                    <p className="text-[11px] text-slate-500 mt-1 truncate">{formatMemoryPath(item)}</p>
                                                                </div>
                                                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 shrink-0">
                                                                    {formatDate(item.data_atualizacao || item.data_criacao)}
                                                                </span>
                                                            </div>
                                                        </button>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                    </section>
                )}

                {/* Items Grid/List */}
                <div
                    className="flex-1 overflow-y-auto p-8 custom-scrollbar relative select-none"
                    onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
                    ref={(el) => {
                        if (el && el.clientWidth !== containerWidth) {
                            setContainerWidth(el.clientWidth);
                        }
                    }}
                    onMouseDown={(e) => {
                        if (e.button !== 0) return;
                        const target = e.target as HTMLElement;
                        if (target.closest('[data-knowledge-item-id]')) return;
                        if (target.closest('button, a, input, textarea, select, label')) return;

                        const rect = e.currentTarget.getBoundingClientRect();
                        const start = {
                            x: e.clientX - rect.left + e.currentTarget.scrollLeft,
                            y: e.clientY - rect.top + e.currentTarget.scrollTop
                        };

                        e.preventDefault();
                        setLassoStart(start);
                        setLassoCurrent(start);

                        const additive = e.ctrlKey || e.metaKey || e.shiftKey;
                        lassoIsAdditiveRef.current = additive;
                        lassoBaseSelectionRef.current = new Set(selectedItems);

                        if (!additive) setSelectedItems(new Set());
                    }}
                    onMouseMove={(e) => {
                        if (lassoStart) {
                            const rect = e.currentTarget.getBoundingClientRect();
                            const current = {
                                x: e.clientX - rect.left + e.currentTarget.scrollLeft,
                                y: e.clientY - rect.top + e.currentTarget.scrollTop
                            };
                            setLassoCurrent(current);

                            const lassoRect = {
                                top: Math.min(lassoStart.y, current.y),
                                bottom: Math.max(lassoStart.y, current.y),
                                left: Math.min(lassoStart.x, current.x),
                                right: Math.max(lassoStart.x, current.x)
                            };

                            const intersectingIds = getIntersectingItemIds(e.currentTarget, lassoRect);
                            if (lassoIsAdditiveRef.current) {
                                const merged = new Set(lassoBaseSelectionRef.current);
                                intersectingIds.forEach((id) => merged.add(id));
                                setSelectedItems(merged);
                            } else {
                                setSelectedItems(intersectingIds);
                            }
                        }
                    }}
                    onMouseUp={() => {
                        setLassoStart(null);
                        setLassoCurrent(null);
                        lassoIsAdditiveRef.current = false;
                    }}
                    onMouseLeave={() => {
                        setLassoStart(null);
                        setLassoCurrent(null);
                        lassoIsAdditiveRef.current = false;
                    }}
                    onDragOver={(e) => e.preventDefault()}
                >
                    {activeTab === 'master' ? (
                        <div className="space-y-12 animate-in fade-in slide-in-from-bottom-8 duration-500 pb-24">
                            <div className="bg-gradient-to-br from-violet-600 to-indigo-700 p-12 rounded-[2.5rem] text-white shadow-2xl relative overflow-hidden">
                                <div className="absolute top-0 right-0 w-64 h-64 bg-white/10 rounded-full -mr-20 -mt-20 blur-3xl"></div>
                                <div className="relative z-10">
                                    <h2 className="text-4xl font-black tracking-tight mb-4">Manual do HERMES</h2>
                                    <p className="text-violet-100 font-medium max-w-2xl text-lg leading-relaxed">
                                        Conhecimentos sintetizados automaticamente pela IA a partir das suas rotinas, processos e documentos.
                                    </p>
                                </div>
                            </div>

                            {masterKnowledge.length === 0 ? (
                                <div className="py-24 text-center bg-white rounded-[2.5rem] border-2 border-dashed border-slate-100">
                                    <div className="w-20 h-20 bg-slate-50 text-slate-300 rounded-3xl flex items-center justify-center mx-auto mb-6">
                                        <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                                    </div>
                                    <p className="text-slate-400 font-black text-xl uppercase tracking-widest">Nenhum padrão sintetizado ainda</p>
                                    <p className="text-slate-300 text-sm mt-2 font-medium">Use o botão "Sintetizar Conhecimento IA" em um módulo para começar.</p>
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                    {masterKnowledge.map((master) => (
                                        <div key={master.id} className="bg-white border border-slate-200 rounded-[2.5rem] p-8 shadow-sm hover:shadow-xl transition-all group flex flex-col h-full border-t-8 border-t-violet-500 overflow-hidden relative">
                                            <div className="absolute top-0 right-0 p-6 text-slate-100 rotate-12 -mr-4 -mt-4 opacity-10 group-hover:rotate-0 group-hover:opacity-20 transition-all">
                                                 <svg className="w-24 h-24" fill="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                            </div>
                                            <div className="relative z-10 flex flex-col h-full">
                                                <div className="flex justify-between items-start mb-6">
                                                    <span className="bg-violet-100 text-violet-700 text-[10px] font-black px-4 py-1.5 rounded-full uppercase tracking-widest">
                                                        {master.categoria}
                                                    </span>
                                                    <span className="text-[10px] font-bold text-slate-400 uppercase">{formatDate(master.data_criacao)}</span>
                                                </div>
                                                <h3 className="text-2xl font-black text-slate-900 mb-4 group-hover:text-violet-600 transition-colors leading-tight">
                                                    {master.titulo}
                                                </h3>
                                                <div className="prose prose-slate prose-sm max-w-none text-slate-600 font-medium leading-relaxed mb-8 flex-1 overflow-y-auto max-h-[300px]">
                                                    <div dangerouslySetInnerHTML={{ __html: master.conteudo.replace(/\n/g, '<br/>') }} />
                                                </div>
                                                <div className="pt-6 border-t border-slate-50 flex items-center justify-between">
                                                    <div className="flex items-center gap-2">
                                                        <div className="w-8 h-8 rounded-full bg-violet-600 flex items-center justify-center text-white text-xs font-black">H</div>
                                                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Sintetizado por HERMES</span>
                                                    </div>
                                                    {onNavigateToOrigin && master.origem && (
                                                        <button 
                                                            onClick={() => onNavigateToOrigin(master.origem.modulo, master.origem.id_origem)}
                                                            className="text-violet-600 hover:text-violet-800 text-[10px] font-black uppercase tracking-widest flex items-center gap-2"
                                                        >
                                                            Ver Origem
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
                                                        </button>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    ) : (
                    <>
                    {lassoStart && lassoCurrent && (
                        <div
                            className="absolute bg-blue-500/20 border border-blue-500 pointer-events-none z-[100]"
                            style={{
                                left: Math.min(lassoStart.x, lassoCurrent.x),
                                top: Math.min(lassoStart.y, lassoCurrent.y),
                                width: Math.abs(lassoCurrent.x - lassoStart.x),
                                height: Math.abs(lassoCurrent.y - lassoStart.y)
                            }}
                        />
                    )}
                    {viewMode === 'grid' ? (() => {
                        const totalRows = Math.ceil(currentItems.length / gridCols);
                        const startRow = Math.max(0, Math.floor(scrollTop / itemHeightGrid) - 2);
                        const endRow = Math.min(totalRows, startRow + Math.ceil(800 / itemHeightGrid) + 4);
                        const visibleItems = currentItems.slice(startRow * gridCols, endRow * gridCols);
                        const topSpacer = startRow * itemHeightGrid;
                        const bottomSpacer = Math.max(0, (totalRows - endRow) * itemHeightGrid);

                        return (
                            <div style={{ paddingBottom: '4rem' }}>
                                <div style={{ height: topSpacer }} />
                                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
                                    {visibleItems.map(item => (
                                        <div
                                            key={item.id}
                                            data-knowledge-item-id={item.id}
                                            draggable={!isVirtualItem(item)}
                                            onDragStart={(e) => {
                                                e.dataTransfer.setData("text/plain", item.id);
                                                if (!item.fileHandle && item.url_drive && !item.is_folder) {
                                                    const ext = item.titulo.includes('.') ? '' : '.pdf';
                                                    e.dataTransfer.setData('DownloadURL', `application/octet-stream:${item.titulo}${ext}:${item.url_drive}`);
                                                }
                                            }}
                                            onDragOver={(e) => item.is_folder ? e.preventDefault() : null}
                                            onDrop={(e) => {
                                                if (item.is_folder) {
                                                    handleDrop(e, item.id);
                                                    e.stopPropagation();
                                                }
                                            }}
                                            onClick={(e) => handleItemClick(e, item)}
                                            onContextMenu={(e) => handleContextMenu(e, item)}
                                            className={`bg-white p-4 rounded-2xl border ${selectedItems.has(item.id) ? 'border-blue-500 shadow-md ring-2 ring-blue-100' : 'border-slate-100 shadow-sm hover:shadow-lg hover:border-blue-200'} transition-all cursor-pointer group flex flex-col items-center text-center gap-3 relative ${item.is_folder ? 'bg-amber-50/10' : ''}`}
                                        >
                                            <div className={`absolute top-3 left-3 z-10 transition-opacity flex items-center shrink-0 ${selectedItems.has(item.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
                                                <input 
                                                    type="checkbox"
                                                    checked={selectedItems.has(item.id)}
                                                    onChange={(e) => {
                                                        e.stopPropagation();
                                                        const next = new Set(selectedItems);
                                                        if (e.target.checked) next.add(item.id);
                                                        else next.delete(item.id);
                                                        setSelectedItems(next);
                                                    }}
                                                    onClick={(e) => e.stopPropagation()}
                                                    className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                                                />
                                            </div>
                                            <div className={`p-3 rounded-2xl transition-colors ${item.is_folder ? 'text-amber-400' : 'bg-slate-50 group-hover:bg-blue-50'}`}>
                                                {getFileIcon(item)}
                                            </div>
                                            <div className="min-w-0 w-full">
                                                {renamingItemId === item.id ? (
                                                    <input
                                                        autoFocus
                                                        type="text"
                                                        className="w-full text-xs font-bold text-slate-900 bg-white border border-blue-500 rounded px-2 py-1 outline-none text-center"
                                                        defaultValue={item.titulo}
                                                        onBlur={async (e) => {
                                                            await handleRenameEntity(item, e.target.value);
                                                            setRenamingItemId(null);
                                                        }}
                                                        onKeyDown={(e) => {
                                                            if (e.key === 'Enter') e.currentTarget.blur();
                                                            if (e.key === 'Escape') setRenamingItemId(null);
                                                        }}
                                                        onClick={(e) => e.stopPropagation()}
                                                    />
                                                ) : (
                                                    <h4 className="text-xs font-bold text-slate-700 leading-tight truncate px-2" onDoubleClick={(e) => { e.stopPropagation(); startItemRename(item); }}>{item.titulo}</h4>
                                                )}
                                                <p className="text-[9px] text-slate-400 font-bold uppercase mt-1">{item.is_folder ? `${items.filter(i => i.parent_id === item.id).length} itens` : formatSize(item.tamanho || 0)}</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                                <div style={{ height: bottomSpacer }} />
                            </div>
                        );
                    })() : (() => {
                        const startRow = Math.max(0, Math.floor(scrollTop / itemHeightList) - 5);
                        const endRow = Math.min(currentItems.length, startRow + Math.ceil(800 / itemHeightList) + 10);
                        const visibleItems = currentItems.slice(startRow, endRow);
                        const topSpacer = startRow * itemHeightList;
                        const bottomSpacer = Math.max(0, (currentItems.length - endRow) * itemHeightList);

                        return (
                            <div className="bg-white rounded-[2rem] border border-slate-100 overflow-hidden shadow-sm">
                                <table className="w-full text-left" style={{ display: 'block' }}>
                                    <thead className="bg-slate-50 border-b border-slate-100" style={{ display: 'table', width: '100%', tableLayout: 'fixed' }}>
                                        <tr>
                                            <th className="pl-6 pr-3 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest text-left">Nome</th>
                                            <th className="px-3 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest text-right" style={{ width: listSizeColWidth }}>Tamanho</th>
                                            <th className="hidden md:table-cell px-3 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest text-right" style={{ width: listModifiedColWidth }}>Modificado</th>
                                            <th style={{ width: listActionsColWidth }} className="pr-6 pl-3 py-4"></th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-50" style={{ display: 'block', height: currentItems.length * itemHeightList, position: 'relative' }}>
                                        {visibleItems.map((item, idx) => (
                                            <tr
                                                key={item.id}
                                                data-knowledge-item-id={item.id}
                                                style={{ position: 'absolute', top: (startRow + idx) * itemHeightList, width: '100%', display: 'table', tableLayout: 'fixed' }}
                                                draggable={!isVirtualItem(item)}
                                                onDragStart={(e) => {
                                                    e.dataTransfer.setData("text/plain", item.id);
                                                    if (!item.fileHandle && item.url_drive && !item.is_folder) {
                                                        const ext = item.titulo.includes('.') ? '' : '.pdf';
                                                        e.dataTransfer.setData('DownloadURL', `application/octet-stream:${item.titulo}${ext}:${item.url_drive}`);
                                                    }
                                                }}
                                                onDragOver={(e) => item.is_folder ? e.preventDefault() : null}
                                                onDrop={(e) => {
                                                    if (item.is_folder) {
                                                        handleDrop(e, item.id);
                                                        e.stopPropagation();
                                                    }
                                                }}
                                                onClick={(e) => handleItemClick(e, item)}
                                                onContextMenu={(e) => handleContextMenu(e, item)}
                                                className={`${selectedItems.has(item.id) ? 'bg-blue-50/50' : 'hover:bg-slate-50'} transition-colors cursor-pointer group`}
                                            >
                                                <td className="pl-6 pr-3 py-3">
                                                    <div className="flex items-center gap-3 min-w-0">
                                                        <div className={`transition-opacity flex items-center shrink-0 ${selectedItems.has(item.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
                                                            <input 
                                                                type="checkbox"
                                                                checked={selectedItems.has(item.id)}
                                                                onChange={(e) => {
                                                                    e.stopPropagation();
                                                                    const next = new Set(selectedItems);
                                                                    if (e.target.checked) next.add(item.id);
                                                                    else next.delete(item.id);
                                                                    setSelectedItems(next);
                                                                }}
                                                                onClick={(e) => e.stopPropagation()}
                                                                className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                                                            />
                                                        </div>
                                                        <div className={`w-8 h-8 flex items-center justify-center shrink-0 transition-opacity ${selectedItems.has(item.id) ? 'hidden' : 'group-hover:hidden'}`}>
                                                            {getFileIcon(item)}
                                                        </div>
                                                        {renamingItemId === item.id ? (
                                                            <input
                                                                autoFocus
                                                                type="text"
                                                                className="min-w-0 flex-1 bg-white border border-blue-400 rounded px-2 py-1 text-xs font-bold text-slate-800 outline-none"
                                                                defaultValue={item.titulo}
                                                                onBlur={async (e) => {
                                                                    await handleRenameEntity(item, e.target.value);
                                                                    setRenamingItemId(null);
                                                                }}
                                                                onKeyDown={(e) => {
                                                                    if (e.key === 'Enter') e.currentTarget.blur();
                                                                    if (e.key === 'Escape') setRenamingItemId(null);
                                                                }}
                                                                onClick={(e) => e.stopPropagation()}
                                                            />
                                                        ) : (
                                                            <span title={item.titulo} onDoubleClick={(e) => { e.stopPropagation(); startItemRename(item); }} className="min-w-0 flex-1 truncate whitespace-nowrap text-xs font-bold text-slate-700 group-hover:text-blue-600 transition-colors">
                                                                {item.titulo}
                                                            </span>
                                                        )}
                                                    </div>
                                                </td>
                                                <td className="px-3 py-3 text-[10px] font-bold text-slate-400 text-right whitespace-nowrap" style={{ width: listSizeColWidth }}>{item.is_folder ? '-' : formatSize(item.tamanho || 0)}</td>
                                                <td className="hidden md:table-cell px-3 py-3 text-[10px] font-bold text-slate-400 uppercase text-right whitespace-nowrap" style={{ width: listModifiedColWidth }}>{formatDate(item.data_criacao?.split('T')[0])}</td>
                                                <td className="pl-3 pr-6 py-3 text-right" style={{ width: listActionsColWidth }}>
                                                    <div className="flex items-center justify-end gap-2">
                                                        {!item.is_folder && item.tipo_arquivo !== 'link' && Boolean(item.url_drive) && !isVirtualItem(item) && (
                                                            <a href={item.url_drive} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="p-2 text-slate-300 hover:text-emerald-500 transition-colors" title="Download">
                                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                                                            </a>
                                                        )}
                                                        <button
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                if (pendingDeleteItemId !== item.id) {
                                                                    setPendingDeleteItemId(item.id);
                                                                    window.setTimeout(() => setPendingDeleteItemId((current) => (current === item.id ? null : current)), 3500);
                                                                    return;
                                                                }
                                                                setPendingDeleteItemId(null);
                                                                onDeleteItem(item.id);
                                                            }}
                                                            className={`p-2 rounded-lg transition-colors ${pendingDeleteItemId === item.id ? 'bg-rose-500 text-white' : 'text-slate-300 hover:text-rose-500'}`}
                                                            title={pendingDeleteItemId === item.id ? "Confirmar exclusão" : "Excluir"}
                                                        >
                                                            {pendingDeleteItemId === item.id ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>}
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        );
                    })()}
                    </>
                    )}

                    {currentItems.length === 0 && (
                        <div className="py-20 text-center">
                            <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4">
                                <svg className="w-8 h-8 text-slate-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
                            </div>
                            <h3 className="text-sm font-black text-slate-900 tracking-tight">Pasta Vazia</h3>
                            <p className="text-slate-400 text-xs mt-1">Arraste arquivos aqui.</p>
                        </div>
                    )}
                </div>
            </main>

            {/* Context Menu */}
            {contextMenu && (
                <div
                    className="fixed z-[400] bg-white rounded-xl shadow-2xl border border-slate-100 py-2 min-w-[160px] animate-in fade-in zoom-in-95 duration-200"
                    style={{ top: contextMenu.y, left: contextMenu.x }}
                    onClick={(e) => e.stopPropagation()}
                >
                    <div className="px-3 py-1 mb-1 border-b border-slate-50">
                        <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">{selectedItems.size} item(s) selecionado(s)</span>
                    </div>
                    {selectedItems.size === 1 && (
                        <button
                            className="w-full text-left px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 transition-colors flex items-center gap-2"
                            onClick={() => {
                                const item = items.find(i => i.id === Array.from(selectedItems)[0]);
                                if (item && !item.is_folder) setSelectedItem(item);
                                setContextMenu(null);
                            }}
                        >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
                            Pré-visualizar
                        </button>
                    )}
                    <button
                        className="w-full text-left px-4 py-2 text-xs font-bold text-red-600 hover:bg-red-50 transition-colors flex items-center gap-2 mt-1"
                        onClick={() => {
                            const persistedSelectedIds = Array.from(selectedItems).filter(id => items.some(item => item.id === id));
                            if (window.confirm(`Tem certeza que deseja deletar ${persistedSelectedIds.length} item(s)?`)) {
                                persistedSelectedIds.forEach(id => onDeleteItem(id));
                                setSelectedItems(new Set());
                            }
                            setContextMenu(null);
                        }}
                    >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                        Deletar Seleção
                    </button>
                </div>
            )}

            {/* Slide-over Preview (File Details) */}
            {currentItem && !currentItem.is_folder && (
                <div className="fixed inset-0 z-[200] flex justify-end animate-in fade-in duration-300">
                    <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setSelectedItem(null)}></div>
                    <div className="relative w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right-full duration-500">
                        <header className="p-8 border-b border-slate-100 flex items-center justify-between flex-shrink-0">
                            <div className="flex items-center gap-4">
                                <div className="p-3 bg-slate-100 rounded-2xl">
                                    {getFileIcon(currentItem)}
                                </div>
                                <div>
                                    <h3 className="text-xl font-black text-slate-900 tracking-tight leading-tight">{currentItem.titulo}</h3>
                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] mt-1">{currentItem.categoria || 'Geral'} • {formatSize(currentItem.tamanho)}</p>
                                </div>
                            </div>
                            <button onClick={() => setSelectedItem(null)} className="p-3 hover:bg-slate-100 rounded-full transition-all">
                                <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </header>

                        <div className="px-8 py-4 border-b border-slate-100 bg-slate-50/70">
                            <div className="flex flex-wrap items-center gap-2 mb-4">
                                <span className="px-3 py-1 rounded-full bg-slate-900 text-white text-[9px] font-black uppercase tracking-[0.2em]">
                                    {currentItem.categoria || 'Geral'}
                                </span>
                                <span className={`px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-[0.2em] ${getProcessingTone(currentItem)}`}>
                                    {getProcessingLabel(currentItem)}
                                </span>
                                {currentItem.resumo_tldr && (
                                    <span className="px-3 py-1 rounded-full bg-blue-100 text-blue-700 text-[9px] font-black uppercase tracking-[0.2em]">
                                        Resumido
                                    </span>
                                )}
                                {currentItem.memory_location && (
                                    <span className="px-3 py-1 rounded-full bg-emerald-100 text-emerald-700 text-[9px] font-black uppercase tracking-[0.2em]">
                                        MemPalace
                                    </span>
                                )}
                            </div>
                            <div className="flex gap-2 overflow-x-auto no-scrollbar">
                                {[
                                    { id: 'overview', label: 'Visão geral' },
                                    { id: 'content', label: 'Conteúdo' },
                                    { id: 'history', label: 'Histórico' },
                                    { id: 'graph', label: 'Relações' },
                                ].map(tab => (
                                    <button
                                        key={tab.id}
                                        onClick={() => setDetailTab(tab.id as typeof detailTab)}
                                        className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] transition-all whitespace-nowrap ${detailTab === tab.id ? 'bg-white text-slate-900 shadow-sm border border-slate-200' : 'text-slate-500 hover:text-slate-700 hover:bg-white/60'}`}
                                    >
                                        {tab.label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar space-y-10">
                            {detailTab === 'overview' && (
                                <section className="bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white rounded-[2rem] p-6 shadow-xl">
                                    <div className="flex flex-col gap-6">
                                        <div>
                                            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-300">Painel operacional</p>
                                            <h4 className="text-2xl font-black tracking-tight mt-2">Use este item como memória viva</h4>
                                            <p className="text-sm text-slate-300 font-medium mt-2 max-w-2xl">
                                                Proveniência, localização no MemPalace, histórico e relações estão reunidos para facilitar decisão, reuso e contextualização.
                                            </p>
                                        </div>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                            <div className="rounded-2xl bg-white/10 border border-white/10 p-4">
                                                <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-300">Proveniência</p>
                                                <p className="text-sm font-bold mt-2 break-words">{formatOriginLabel(currentItem)}</p>
                                            </div>
                                            <div className="rounded-2xl bg-white/10 border border-white/10 p-4">
                                                <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-300">MemPalace</p>
                                                <p className="text-sm font-bold mt-2 break-words">{formatMemoryPath(currentItem)}</p>
                                            </div>
                                        </div>
                                        <div className="flex flex-wrap gap-3">
                                            {onProcessWithAI && (
                                                <button onClick={handleProcessCurrentItemWithAI} disabled={isProcessingAI} className="px-4 py-3 rounded-2xl bg-blue-500 hover:bg-blue-400 text-white text-[10px] font-black uppercase tracking-[0.2em] transition-all disabled:opacity-50">
                                                    {isProcessingAI ? 'Processando...' : 'Processar com IA'}
                                                </button>
                                            )}
                                            {onGenerateSlides && (currentItem.texto_bruto || currentItem.resumo_tldr) && (
                                                <button onClick={handleGenerateCurrentSlides} className="px-4 py-3 rounded-2xl bg-violet-500 hover:bg-violet-400 text-white text-[10px] font-black uppercase tracking-[0.2em] transition-all">
                                                    Gerar slides
                                                </button>
                                            )}
                                            {onNavigateToOrigin && currentItem.origem && (
                                                <button onClick={() => onNavigateToOrigin(currentItem.origem!.modulo, currentItem.origem!.id_origem)} className="px-4 py-3 rounded-2xl bg-white/10 hover:bg-white/20 text-white text-[10px] font-black uppercase tracking-[0.2em] transition-all">
                                                    Ir para origem
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                </section>
                            )}

                            {/* Native Previews for Desktop UX */}
                            {(detailTab === 'overview' || detailTab === 'content') && currentItem.tipo_arquivo === 'pdf' && currentItem.url_drive && (
                                <section className="w-full bg-slate-50 rounded-[2rem] p-8 border-2 border-dashed border-slate-200 flex flex-col items-center justify-center text-center gap-4">
                                    <div className="w-16 h-16 bg-blue-100 text-blue-600 rounded-2xl flex items-center justify-center mb-2">
                                        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                    </div>
                                    <div>
                                        <h4 className="text-lg font-black text-slate-800">Visualização de Documento</h4>
                                        <p className="text-sm font-bold text-slate-500 max-w-sm mt-2">Para visualizar o arquivo com segurança e evitar bloqueios de permissão do Google Drive, abra-o em uma nova guia.</p>
                                    </div>
                                    <a href={currentItem.url_drive} target="_blank" rel="noopener noreferrer" className="mt-2 bg-blue-600 text-white px-8 py-4 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all flex items-center gap-2">
                                        Abrir no Google Drive
                                    </a>
                                </section>
                            )}

                            {(detailTab === 'overview' || detailTab === 'content') && currentItem.tipo_arquivo === 'imagem' && currentItem.url_drive && (
                                <section className="flex justify-center bg-slate-100 rounded-[2rem] p-4 border border-slate-200">
                                    <img src={currentItem.url_drive} alt="Preview" className="max-h-96 object-contain rounded-xl shadow-sm" loading="lazy" />
                                </section>
                            )}

                            {/* Same content viewers as before */}
                            {(detailTab === 'overview' || detailTab === 'content') && currentItem.tipo_arquivo === 'link' && (
                                <section>
                                    <div className="bg-blue-50 p-6 rounded-[2rem] border border-blue-100 flex items-center justify-between">
                                        <div className="overflow-hidden">
                                            <p className="text-xs font-black text-blue-900 uppercase tracking-widest mb-1">URL de Destino</p>
                                            <a href={currentItem.url_drive} target="_blank" rel="noopener noreferrer" className="text-sm font-bold text-blue-600 truncate block hover:underline">
                                                {currentItem.url_drive}
                                            </a>
                                        </div>
                                        <a href={currentItem.url_drive} target="_blank" rel="noopener noreferrer" className="p-3 bg-blue-600 text-white rounded-xl shadow-lg hover:bg-blue-700 transition-all shrink-0 ml-4">
                                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                        </a>
                                    </div>
                                </section>
                            )}

                            {/* Resumo TLDR */}
                            {detailTab === 'overview' && currentItem.resumo_tldr && (
                                <section>
                                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4 border-l-4 border-blue-500 pl-4">Resumo Executivo (TL;DR)</h4>
                                    <div className="bg-blue-50/50 p-6 rounded-[2rem] border border-blue-100 text-sm text-blue-900 font-medium leading-relaxed italic">
                                        {currentItem.resumo_tldr}
                                    </div>
                                </section>
                            )}

                            {detailTab === 'overview' && <section>
                                <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4 border-l-4 border-emerald-500 pl-4">Metadados do Documento</h4>
                                <div className="bg-emerald-50/40 p-6 rounded-[2rem] border border-emerald-100 grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div>
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Versão</p>
                                        <p className="text-sm font-bold text-slate-900">{currentItem.version || 1}</p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Atualizado Em</p>
                                        <p className="text-sm font-bold text-slate-900">{currentItem.data_atualizacao ? formatDate(currentItem.data_atualizacao) : 'Ainda não atualizado'}</p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Canal de Entrada</p>
                                        <p className="text-sm font-bold text-slate-900">{currentItem.intake_record?.channel || 'Não informado'}</p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Status de Processamento</p>
                                        <p className="text-sm font-bold text-slate-900">{currentItem.intake_record?.processing_status || 'Não informado'}</p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Origem do Artefato</p>
                                        <p className="text-sm font-bold text-slate-900">{currentItem.artifact_origin_kind || 'Não informado'}</p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Fonte / Proveniência</p>
                                        <p className="text-sm font-bold text-slate-900 break-words">{formatOriginLabel(currentItem)}</p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">MemPalace</p>
                                        <p className="text-sm font-bold text-slate-900 break-words">
                                            {currentItem.memory_location
                                                ? [currentItem.memory_location.wing, currentItem.memory_location.room, currentItem.memory_location.drawer, currentItem.memory_location.cabinet]
                                                    .filter(Boolean)
                                                    .join(' / ')
                                                : 'Não localizado'}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Última Mudança</p>
                                        <p className="text-sm font-bold text-slate-900">{formatUpdateReason(currentItem.last_update_reason)}</p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Atualizado Por</p>
                                        <p className="text-sm font-bold text-slate-900">{currentItem.last_updated_by || 'Não informado'}</p>
                                    </div>
                                </div>
                            </section>}

                            {detailTab === 'history' && versionHistory.length > 0 && (
                                <section>
                                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4 border-l-4 border-amber-500 pl-4">Histórico Recente</h4>
                                    <div className="space-y-2">
                                        {versionHistory.map((entry) => {
                                            const changedLabel = formatChangedFields(entry.changed_fields);
                                            const preview = entry.resumo_tldr || entry.titulo;
                                            return (
                                                <div key={entry.id} className="bg-amber-50/40 border border-amber-100 rounded-2xl p-3">
                                                    <div className="flex items-center justify-between gap-3">
                                                        <p className="text-xs font-black text-slate-900">v{entry.version} · {formatUpdateReason(entry.reason)}</p>
                                                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest shrink-0">{entry.captured_at ? formatDate(entry.captured_at) : 'sem data'}</p>
                                                    </div>
                                                    {changedLabel && (
                                                        <p className="text-[10px] text-amber-700 font-semibold mt-1">alterou: {changedLabel}</p>
                                                    )}
                                                    {preview && (
                                                        <p className="text-[11px] text-slate-500 mt-1 line-clamp-2">{preview}</p>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>
                                </section>
                            )}

                            {/* ── Relações (Fase 2B) ──────────────────────── */}
                            {detailTab === 'graph' && <section className="space-y-6">
                                <div className="h-[400px] w-full rounded-[2rem] overflow-hidden border border-slate-100 bg-slate-50 relative group">
                                    <KnowledgeGraphView 
                                        items={items} 
                                        edges={edges} 
                                        width={600} 
                                        height={400} 
                                        onNodeClick={(node) => {
                                            const item = items.find(i => i.id === node.id);
                                            if (item) setSelectedItem(item);
                                        }}
                                    />
                                    <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <div className="bg-slate-900/80 backdrop-blur-md text-white px-3 py-1.5 rounded-full text-[9px] font-black uppercase tracking-widest">
                                            Interactive Graph
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center justify-between mb-4 border-l-4 border-violet-500 pl-4">
                                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">
                                        Tabela de Relações
                                        {edges.length > 0 && (
                                            <span className="ml-2 bg-violet-100 text-violet-700 text-[9px] font-black rounded-full px-2 py-0.5">
                                                {edges.length}
                                            </span>
                                        )}
                                    </h4>
                                    <button
                                        onClick={() => { setIsAddingEdge(v => !v); setNewEdgeTargetId(''); setNewEdgeRelation('related_to'); setNewEdgeValidFrom(''); setNewEdgeValidUntil(''); }}
                                        className="p-1.5 hover:bg-violet-50 rounded-lg text-violet-500 hover:text-violet-700 transition-all"
                                        title="Adicionar relação"
                                    >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                                    </button>
                                </div>

                                {/* Add edge form */}
                                {isAddingEdge && (
                                    <div className="bg-violet-50/60 border border-violet-100 rounded-2xl p-4 mb-3 space-y-3">
                                        <div>
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1">Item relacionado</label>
                                            <select
                                                value={newEdgeTargetId}
                                                onChange={e => setNewEdgeTargetId(e.target.value)}
                                                className="w-full text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-300"
                                            >
                                                <option value="">Selecionar item…</option>
                                                {items
                                                    .filter(i => !i.is_folder && i.id !== currentItem.id)
                                                    .sort((a, b) => a.titulo.localeCompare(b.titulo, 'pt-BR'))
                                                    .map(i => (
                                                        <option key={i.id} value={i.id}>{i.titulo}</option>
                                                    ))}
                                            </select>
                                        </div>
                                        <div>
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1">Tipo de relação</label>
                                            <select
                                                value={newEdgeRelation}
                                                onChange={e => setNewEdgeRelation(e.target.value as RelationKind)}
                                                className="w-full text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-300"
                                            >
                                                {(Object.keys(RELATION_KIND_LABELS) as RelationKind[]).map(k => (
                                                    <option key={k} value={k}>{RELATION_KIND_LABELS[k]}</option>
                                                ))}
                                            </select>
                                        </div>
                                        <div className="grid grid-cols-2 gap-3">
                                            <div>
                                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1">Válido de</label>
                                                <input
                                                    type="date"
                                                    value={newEdgeValidFrom}
                                                    onChange={e => setNewEdgeValidFrom(e.target.value)}
                                                    className="w-full text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-300"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1">Válido até</label>
                                                <input
                                                    type="date"
                                                    value={newEdgeValidUntil}
                                                    onChange={e => setNewEdgeValidUntil(e.target.value)}
                                                    className="w-full text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-300"
                                                />
                                            </div>
                                        </div>
                                        <div className="flex justify-end gap-2">
                                            <button
                                                onClick={() => setIsAddingEdge(false)}
                                                className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-100 rounded-xl transition-all"
                                            >
                                                Cancelar
                                            </button>
                                            <button
                                                onClick={handleAddEdge}
                                                disabled={!newEdgeTargetId}
                                                className="px-4 py-2 text-[10px] font-black uppercase tracking-widest bg-violet-600 text-white rounded-xl hover:bg-violet-700 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                                            >
                                                Adicionar
                                            </button>
                                        </div>
                                    </div>
                                )}

                                {/* Edge list */}
                                {edges.length === 0 && !isAddingEdge ? (
                                    <p className="text-xs text-slate-400 font-semibold text-center py-4">Nenhuma relação registrada.</p>
                                ) : (
                                    <div className="space-y-2">
                                        {edges.map(edge => {
                                            const isSource = edge.source_id === currentItem.id;
                                            const otherId = isSource ? edge.target_id : edge.source_id;
                                            const otherItem = items.find(i => i.id === otherId);
                                            const active = isEdgeActive(edge);
                                            return (
                                                <div
                                                    key={edge.id}
                                                    className={`flex items-start gap-3 p-3 rounded-2xl border transition-all ${active ? 'bg-white border-slate-100' : 'bg-slate-50 border-slate-100 opacity-60'}`}
                                                >
                                                    {/* Direction arrow */}
                                                    <div className="shrink-0 mt-0.5">
                                                        <svg className={`w-4 h-4 ${isSource ? 'text-violet-400' : 'text-slate-300'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            {isSource
                                                                ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M17 8l4 4m0 0l-4 4m4-4H3" />
                                                                : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M7 16l-4-4m0 0l4-4m-4 4h18" />
                                                            }
                                                        </svg>
                                                    </div>
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2 flex-wrap">
                                                            <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${RELATION_KIND_COLORS[edge.relation_kind]}`}>
                                                                {RELATION_KIND_LABELS[edge.relation_kind]}
                                                            </span>
                                                            {!active && (
                                                                <span className="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-slate-100 text-slate-400">
                                                                    Expirada
                                                                </span>
                                                            )}
                                                        </div>
                                                        <p className="text-xs font-bold text-slate-900 mt-1 truncate">
                                                            {otherItem?.titulo ?? otherId}
                                                        </p>
                                                        {(edge.valid_from || edge.valid_until) && (
                                                            <p className="text-[10px] text-slate-400 font-semibold mt-0.5">
                                                                {edge.valid_from && `de ${edge.valid_from}`}
                                                                {edge.valid_from && edge.valid_until && ' '}
                                                                {edge.valid_until && `até ${edge.valid_until}`}
                                                            </p>
                                                        )}
                                                    </div>
                                                    <button
                                                        onClick={() => handleRemoveEdge(edge.id)}
                                                        className="shrink-0 p-1.5 hover:bg-rose-50 rounded-lg text-slate-300 hover:text-rose-500 transition-all"
                                                        title="Remover relação"
                                                    >
                                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                                                    </button>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </section>}

                            {/* OCR / Editor */}
                            {detailTab === 'content' && (currentItem.texto_bruto || editOcrText !== null || currentItem.fileHandle) && (
                                <section>
                                    <div className="flex items-center justify-between mb-4 border-l-4 border-slate-900 pl-4">
                                        <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">{editOcrText !== null ? 'Modo Edição' : 'Conteúdo / OCR'}</h4>
                                        <div className="flex gap-2">
                                            {editOcrText === null ? (
                                                <>
                                                    <button
                                                        onClick={() => setEditOcrText(currentItem.texto_bruto || '')}
                                                        className="p-2 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-blue-600 transition-all"
                                                        title="Editar texto"
                                                    >
                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                    </button>
                                                    <button
                                                        onClick={() => handleCopyToClipboard(currentItem.texto_bruto || '')}
                                                        className="p-2 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-600 transition-all"
                                                        title="Copiar texto"
                                                    >
                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>
                                                    </button>
                                                    <button
                                                        onClick={() => setIsOcrExpanded(!isOcrExpanded)}
                                                        className="p-2 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-600 transition-all font-black text-[9px] uppercase tracking-widest"
                                                    >
                                                        {isOcrExpanded ? 'Recolher' : 'Expandir'}
                                                    </button>
                                                </>
                                            ) : (
                                                <>
                                                    <button
                                                        onClick={() => setEditOcrText(null)}
                                                        className="p-2 hover:bg-slate-100 rounded-lg text-slate-400 transition-all font-black text-[9px] uppercase tracking-widest"
                                                    >
                                                        Cancelar
                                                    </button>
                                                    <button
                                                        onClick={async () => {
                                                            try {
                                                                if (onSaveItem) {
                                                                    await onSaveItem({ id: currentItem.id, texto_bruto: editOcrText });
                                                                }
                                                                // Sync back to local OS disk via File System API if linked
                                                                // To retrieve the original fileHandle we lookup in IndexedDB
                                                                const handle = await idb.get(`fileHandle_${currentItem.id}`);
                                                                if (handle) {
                                                                    // Request permission again if needed
                                                                    if (await handle.queryPermission({ mode: 'readwrite' }) !== 'granted') {
                                                                        await handle.requestPermission({ mode: 'readwrite' });
                                                                    }
                                                                    const writable = await handle.createWritable();
                                                                    await writable.write(editOcrText);
                                                                    await writable.close();
                                                                    alert('Arquivo local atualizado com sucesso via File System Access API!');
                                                                }
                                                                setEditOcrText(null);
                                                            } catch (err) {
                                                                console.error("Failed to save", err);
                                                                alert('Falha ao salvar o arquivo local. Verifique as permissões de acesso ao disco.');
                                                            }
                                                        }}
                                                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-all font-black text-[9px] uppercase tracking-widest"
                                                    >
                                                        Salvar
                                                    </button>
                                                </>
                                            )}
                                        </div>
                                    </div>
                                    {editOcrText !== null ? (
                                        <textarea
                                            value={editOcrText}
                                            onChange={(e) => setEditOcrText(e.target.value)}
                                            className="w-full h-96 bg-slate-50 p-6 rounded-[2rem] border border-blue-200 text-sm font-medium text-slate-900 leading-relaxed font-mono outline-none focus:ring-2 focus:ring-blue-500 custom-scrollbar resize-none"
                                        />
                                    ) : (
                                        <div className={`bg-slate-50 p-6 rounded-[2rem] border border-slate-200 text-xs font-medium text-slate-700 leading-relaxed whitespace-pre-wrap font-mono relative overflow-hidden transition-all duration-500 ${isOcrExpanded ? 'max-h-none' : 'max-h-40'}`}>
                                            {currentItem.texto_bruto || 'Sem conteúdo.'}
                                            {!isOcrExpanded && (
                                                <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-slate-50 to-transparent pointer-events-none"></div>
                                            )}
                                        </div>
                                    )}
                                </section>
                            )}
                        </div>

                        <footer className="p-8 border-t border-slate-100 bg-slate-50 flex gap-4">
                            {onProcessWithAI && (!currentItem.resumo_tldr) && currentItem.tipo_arquivo !== 'link' && (
                                <button
                                    onClick={handleProcessCurrentItemWithAI}
                                    disabled={isProcessingAI}
                                    className={`flex-1 bg-blue-600 text-white py-5 rounded-3xl text-[10px] font-black uppercase tracking-[0.2em] text-center shadow-lg hover:bg-blue-700 transition-all flex items-center justify-center gap-3 disabled:opacity-50`}
                                >
                                    {isProcessingAI ? 'Processando...' : 'Processar com IA'}
                                </button>
                            )}

                            {onGenerateSlides && (currentItem.texto_bruto || currentItem.resumo_tldr) && (
                                <button
                                    onClick={handleGenerateCurrentSlides}
                                    className="flex-1 bg-violet-600 text-white py-5 rounded-3xl text-[10px] font-black uppercase tracking-[0.2em] text-center shadow-lg hover:bg-violet-700 transition-all flex items-center justify-center gap-3"
                                >
                                    Gerar Slides
                                </button>
                            )}

                            {currentItem.tipo_arquivo !== 'link' && Boolean(currentItem.url_drive) && !isVirtualItem(currentItem) && (
                                <a
                                    href={currentItem.url_drive}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="flex-1 bg-slate-900 text-white py-5 rounded-3xl text-[10px] font-black uppercase tracking-[0.2em] text-center shadow-lg hover:bg-slate-800 transition-all flex items-center justify-center gap-3"
                                >
                                    Abrir no Drive
                                </a>
                            )}
                        </footer>
                    </div>
                </div>
            )}

            {/* Create Folder Modal */}
            {isNewFolderModalOpen && (
                <div className="fixed inset-0 z-[300] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-300">
                    <div className="bg-white w-full max-w-sm rounded-[2rem] shadow-2xl p-8 animate-in zoom-in-95">
                        <h3 className="text-lg font-black text-slate-900 tracking-tight mb-4">Nova Pasta</h3>
                        <input
                            type="text"
                            value={newFolderName}
                            onChange={e => setNewFolderName(e.target.value)}
                            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 mb-6"
                            placeholder="Nome da pasta"
                            autoFocus
                        />
                        <div className="flex gap-4">
                            <button onClick={() => setIsNewFolderModalOpen(false)} className="flex-1 py-3 text-[10px] font-black uppercase text-slate-400 hover:bg-slate-50 rounded-xl">Cancelar</button>
                            <button
                                onClick={() => {
                                    if (onSaveItem && newFolderName) {
                                        const destinationPatch = getDestinationPatch(currentFolderId);
                                        // Creating a new folder requires a new ID.
                                        // We can't generate it here reliably without Firestore refs if we want to follow 'onSave' pattern.
                                        // We will pass a special "new" flag or object.
                                        // Actually, `onSaveItem` takes `Partial<ConhecimentoItem>`.
                                        // If ID is missing, `App` should handle creation?
                                        // Let's assume we pass a random ID for now or `App` handles it.
                                        // `index.tsx` logic: `if (item.id) updateDoc...`. It DOES NOT handle create.
                                        // I need to add `onCreateFolder` prop to `KnowledgeView` and handle it in `App`.
                                        // But I am writing `KnowledgeView` NOW. I will add the prop to interface.
                                        // BUT I cannot change `App` in this step.
                                        // I will trigger `onSaveItem` with a generated ID.
                                        const newId = `folder_${Date.now()}`;
                                        onSaveItem({
                                            id: newId,
                                            titulo: newFolderName,
                                            is_folder: true,
                                            parent_id: destinationPatch.parent_id || null,
                                            tipo_arquivo: 'folder',
                                            data_criacao: new Date().toISOString(),
                                            tamanho: 0,
                                            url_drive: '',
                                            ...(destinationPatch.categoria ? { categoria: destinationPatch.categoria } : {}),
                                            ...(destinationPatch.origem ? { origem: destinationPatch.origem } : {})
                                        });
                                        setNewFolderName('');
                                        setIsNewFolderModalOpen(false);
                                    }
                                }}
                                disabled={!newFolderName}
                                className="flex-1 bg-blue-600 text-white py-3 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all disabled:opacity-50"
                            >
                                Criar
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Link Modal */}
            {isLinkModalOpen && (
                <div className="fixed inset-0 z-[300] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-300">
                    <div className="bg-white w-full max-w-lg rounded-[2rem] shadow-2xl p-8 animate-in zoom-in-95">
                        <h3 className="text-xl font-black text-slate-900 tracking-tight mb-6">Novo Link</h3>
                        <div className="space-y-4">
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Título</label>
                                <input
                                    type="text"
                                    value={linkTitle}
                                    onChange={e => setLinkTitle(e.target.value)}
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="Ex: Documentação Oficial"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">URL</label>
                                <input
                                    type="text"
                                    value={linkUrl}
                                    onChange={e => setLinkUrl(e.target.value)}
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="https://..."
                                />
                            </div>
                        </div>
                        <div className="flex gap-4 mt-8">
                            <button onClick={() => setIsLinkModalOpen(false)} className="flex-1 py-4 text-[10px] font-black uppercase text-slate-400 hover:bg-slate-50 rounded-2xl">Cancelar</button>
                            <button
                                onClick={async () => {
                                    if (linkUrl && linkTitle && onAddLink) {
                                        await onAddLink(linkUrl, linkTitle, currentFolderId);
                                        setLinkUrl('');
                                        setLinkTitle('');
                                        setIsLinkModalOpen(false);
                                    }
                                }}
                                disabled={!linkUrl || !linkTitle}
                                className="flex-1 bg-blue-600 text-white py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all disabled:opacity-50"
                            >
                                Salvar
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Move Modal */}
            {isMoveModalOpen && (
                <div className="fixed inset-0 z-[300] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-300">
                    <div className="bg-white w-full max-w-lg rounded-[2rem] shadow-2xl p-8 animate-in zoom-in-95 flex flex-col max-h-[80vh]">
                        <h3 className="text-xl font-black text-slate-900 tracking-tight mb-6">Mover {selectedItems.size} item(s)</h3>
                        <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
                            <div className="space-y-1">
                                <button
                                    onClick={() => setMoveTargetFolderId(null)}
                                    className={`w-full flex items-center gap-3 px-4 py-2 rounded-xl transition-all mb-1 ${moveTargetFolderId === null ? 'bg-slate-100 text-slate-900 font-bold' : 'text-slate-500 hover:bg-slate-50'}`}
                                >
                                    <svg className="w-4 h-4 text-amber-400" fill="currentColor" viewBox="0 0 24 24"><path d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" /></svg>
                                    <span className="text-[11px] font-medium">Biblioteca</span>
                                </button>
                                {(sidebarChildrenByParent.get(null) || [])
                                    .map(folder => {
                                        // A simple recursive renderer just for the move modal
                                        const renderMoveFolder = (f: ConhecimentoItem, depth: number) => {
                                            const children = sidebarChildrenByParent.get(f.id) || [];
                                            const isSelected = moveTargetFolderId === f.id;
                                            // Do not show folders that are currently selected to be moved
                                            if (selectedItems.has(f.id)) return null;

                                            return (
                                                <div key={f.id}>
                                                    <button
                                                        onClick={() => setMoveTargetFolderId(f.id)}
                                                        style={{ marginLeft: `${depth * 12}px` }}
                                                        className={`w-full flex items-center gap-2 px-3 py-2 rounded-xl transition-all mb-1 ${isSelected ? 'bg-slate-100 text-slate-900 font-bold' : 'text-slate-500 hover:bg-slate-50'}`}
                                                    >
                                                        <span className="w-4 h-4 min-w-[16px] shrink-0 flex items-center justify-center text-amber-400">
                                                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" /></svg>
                                                        </span>
                                                        <span className="text-[11px] truncate">{f.titulo}</span>
                                                    </button>
                                                    {children.map(child => renderMoveFolder(child, depth + 1))}
                                                </div>
                                            );
                                        };
                                        return renderMoveFolder(folder, 0);
                                    })}
                            </div>
                        </div>
                        <div className="flex gap-4 mt-8 pt-4 border-t border-slate-100 shrink-0">
                            <button onClick={() => setIsMoveModalOpen(false)} className="flex-1 py-4 text-[10px] font-black uppercase text-slate-400 hover:bg-slate-50 rounded-2xl">Cancelar</button>
                            <button
                                onClick={async () => {
                                    if (onSaveItem) {
                                        for (const id of Array.from(selectedItems)) {
                                            const item = items.find(i => i.id === id);
                                            // Make sure we are not moving a file onto itself or a folder onto its own children... simple check for self
                                            if (item && item.id !== moveTargetFolderId) {
                                                await onSaveItem({ id: item.id, parent_id: moveTargetFolderId === 'biblioteca' ? null : moveTargetFolderId });
                                            }
                                        }
                                    }
                                    setSelectedItems(new Set());
                                    setIsMoveModalOpen(false);
                                }}
                                className="flex-1 bg-purple-600 text-white py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-purple-700 transition-all"
                            >
                                Mover para Aqui
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Upload Modal Overlay */}
            {isUploading && (
                <div className="fixed inset-0 z-[500] bg-slate-900/60 backdrop-blur-sm flex items-center justify-center animate-in fade-in">
                    <div className="bg-white p-8 rounded-[2rem] shadow-2xl flex flex-col items-center gap-6 animate-in zoom-in-95">
                        <svg className="w-12 h-12 animate-spin text-blue-600" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <div className="text-center">
                            <p className="text-sm font-black text-slate-800 uppercase tracking-widest mb-1">Enviando Arquivo</p>
                            <p className="text-xs font-bold text-slate-500">Por favor, aguarde...</p>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default KnowledgeView;
