import { ConhecimentoItem, Tarefa } from '../../types';
import { parseDiaryRichNote } from './diaryEntries';

export const ROOT_ACTIONS_FOLDER_ID = '__root_actions__';
export const ROOT_HEALTH_FOLDER_ID = '__root_health__';
export const ROOT_PROJECTS_FOLDER_ID = '__root_projects__';

export const ACTION_FOLDER_PREFIX = '__action_folder__';
export const ACTION_DIARY_PREFIX = '__action_diary__';

export type KnowledgeDomain = 'acoes' | 'saude' | 'projetos';
export type KnowledgeSearchMode = 'all' | 'folders' | 'files';

const ROOT_FOLDER_ORDER = [
    ROOT_ACTIONS_FOLDER_ID,
    ROOT_HEALTH_FOLDER_ID,
    ROOT_PROJECTS_FOLDER_ID
] as const;

const normalizeText = (text?: string | null) =>
    (text || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .trim();

export const isRootKnowledgeFolderId = (folderId?: string | null) =>
    folderId === ROOT_ACTIONS_FOLDER_ID ||
    folderId === ROOT_HEALTH_FOLDER_ID ||
    folderId === ROOT_PROJECTS_FOLDER_ID;

export const isActionVirtualFolderId = (folderId?: string | null): folderId is string =>
    Boolean(folderId && folderId.startsWith(ACTION_FOLDER_PREFIX));

export const getActionVirtualFolderId = (taskId: string) => `${ACTION_FOLDER_PREFIX}${taskId}`;

export const getTaskIdFromActionFolderId = (folderId?: string | null) => {
    if (!isActionVirtualFolderId(folderId)) return null;
    return folderId.slice(ACTION_FOLDER_PREFIX.length);
};

export const getActionDiaryItemId = (taskId: string) => `${ACTION_DIARY_PREFIX}${taskId}`;

export const isActionDiaryItemId = (itemId?: string | null) =>
    Boolean(itemId && itemId.startsWith(ACTION_DIARY_PREFIX));

export function classifyKnowledgeDomain(item: ConhecimentoItem): KnowledgeDomain {
    const category = normalizeText(item.categoria);
    if (category.includes('saude')) return 'saude';
    if (category.includes('acao')) return 'acoes';
    if (category.includes('projeto')) return 'projetos';

    const modulo = normalizeText(item.origem?.modulo);
    if (modulo === 'tarefas' || modulo === 'acoes') return 'acoes';
    if (modulo === 'saude') return 'saude';
    if (modulo === 'projetos' || modulo === 'project' || modulo === 'projects') return 'projetos';

    return 'projetos';
}

const sortItems = (items: ConhecimentoItem[]) => {
    return [...items].sort((a, b) => {
        if (a.is_folder && !b.is_folder) return -1;
        if (!a.is_folder && b.is_folder) return 1;
        return new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime();
    });
};

const buildDiaryText = (task: Tarefa) => {
    const title = task.titulo || `Ação ${task.id}`;
    const entries = [...(task.acompanhamento || [])].sort((a, b) =>
        new Date(a.data).getTime() - new Date(b.data).getTime()
    );

    const lines: string[] = [
        `Diário de bordo da ação: ${title}`,
        `ID da ação: ${task.id}`,
        ''
    ];

    if (entries.length === 0) {
        lines.push('Sem registros no diário de bordo.');
        return lines.join('\n');
    }

    entries.forEach((entry, index) => {
        const parsed = parseDiaryRichNote(entry.nota || '');
        const dateLabel = entry.data
            ? new Date(entry.data).toLocaleString('pt-BR')
            : 'Data não informada';

        let noteText = (entry.nota || '').trim();
        if (parsed) {
            if (parsed.type === 'FILE') noteText = `Arquivo: ${parsed.name || parsed.value} (${parsed.value})`;
            if (parsed.type === 'LINK') noteText = `Link: ${parsed.name || parsed.value} (${parsed.value})`;
            if (parsed.type === 'CONTACT') noteText = `Contato: ${parsed.name || parsed.value} (${parsed.value})`;
        }

        lines.push(`${index + 1}. [${dateLabel}] ${noteText}`);
    });

    return lines.join('\n');
};

const createActionDiaryItem = (task: Tarefa): ConhecimentoItem => {
    const diaryText = buildDiaryText(task);
    return {
        id: getActionDiaryItemId(task.id),
        titulo: `${task.titulo}.txt`,
        tipo_arquivo: 'txt',
        url_drive: '',
        tamanho: diaryText.length,
        data_criacao: task.data_criacao || new Date().toISOString(),
        texto_bruto: diaryText,
        origem: { modulo: 'tarefas', id_origem: task.id },
        categoria: 'Ações'
    };
};

const matchesSearch = (item: ConhecimentoItem, searchTerm: string) => {
    const lowerSearch = searchTerm.toLowerCase();
    return (
        item.titulo.toLowerCase().includes(lowerSearch) ||
        (item.tags && item.tags.some(tag => tag.toLowerCase().includes(lowerSearch))) ||
        (item.texto_bruto && item.texto_bruto.toLowerCase().includes(lowerSearch))
    );
};

export function computeFolderStructure(items: ConhecimentoItem[], allTasks: Tarefa[]) {
    const rootFolders: ConhecimentoItem[] = [
        {
            id: ROOT_ACTIONS_FOLDER_ID,
            titulo: 'Ações',
            is_folder: true,
            tipo_arquivo: 'virtual_folder',
            data_criacao: new Date(0).toISOString(),
            tamanho: 0,
            url_drive: '',
            parent_id: null
        },
        {
            id: ROOT_HEALTH_FOLDER_ID,
            titulo: 'Saúde',
            is_folder: true,
            tipo_arquivo: 'virtual_folder',
            data_criacao: new Date(1).toISOString(),
            tamanho: 0,
            url_drive: '',
            parent_id: null
        },
        {
            id: ROOT_PROJECTS_FOLDER_ID,
            titulo: 'Projetos',
            is_folder: true,
            tipo_arquivo: 'virtual_folder',
            data_criacao: new Date(2).toISOString(),
            tamanho: 0,
            url_drive: '',
            parent_id: null
        }
    ];

    const actionDocTaskIds = new Set(
        items
            .filter(item => classifyKnowledgeDomain(item) === 'acoes' && item.origem?.id_origem)
            .map(item => item.origem!.id_origem)
    );

    const actionTaskFolders = allTasks
        .filter(task => actionDocTaskIds.has(task.id))
        .map(task => ({
            id: getActionVirtualFolderId(task.id),
            titulo: task.titulo,
            is_folder: true,
            tipo_arquivo: 'virtual_folder',
            data_criacao: task.data_criacao,
            tamanho: 0,
            url_drive: '',
            parent_id: ROOT_ACTIONS_FOLDER_ID
        } as ConhecimentoItem));

    const knownTaskIds = new Set(allTasks.map(task => task.id));
    const orphanCustomTitleByTaskId = new Map<string, string>();
    items.forEach((item) => {
        const taskId = item.origem?.id_origem;
        if (!taskId) return;
        if (classifyKnowledgeDomain(item) !== 'acoes') return;
        const customTitle = (item.orphan_action_title || '').trim();
        if (customTitle && !orphanCustomTitleByTaskId.has(taskId)) {
            orphanCustomTitleByTaskId.set(taskId, customTitle);
        }
    });

    const orphanActionFolders = [...actionDocTaskIds]
        .filter(taskId => !knownTaskIds.has(taskId))
        .map(taskId => ({
            id: getActionVirtualFolderId(taskId),
            titulo: orphanCustomTitleByTaskId.get(taskId) || `Ação sem cadastro (${taskId.slice(0, 8)})`,
            is_folder: true,
            tipo_arquivo: 'virtual_folder',
            data_criacao: new Date().toISOString(),
            tamanho: 0,
            url_drive: '',
            parent_id: ROOT_ACTIONS_FOLDER_ID
        } as ConhecimentoItem));

    const realFolders = items.filter(item => item.is_folder);
    return [...rootFolders, ...sortItems(actionTaskFolders), ...sortItems(orphanActionFolders), ...realFolders];
}

export function filterCurrentItems(
    items: ConhecimentoItem[],
    allTasks: Tarefa[],
    folderStructure: ConhecimentoItem[],
    currentFolderId: string | null,
    searchTerm: string,
    searchMode: KnowledgeSearchMode = 'all'
) {
    const actionDocTaskIds = new Set(
        items
            .filter(item => classifyKnowledgeDomain(item) === 'acoes' && item.origem?.id_origem)
            .map(item => item.origem!.id_origem)
    );

    const diaryItems = allTasks
        .filter(task => actionDocTaskIds.has(task.id))
        .map(task => createActionDiaryItem(task));

    if (searchTerm) {
        const folderResults =
            searchMode === 'files'
                ? []
                : folderStructure.filter(folder => matchesSearch(folder, searchTerm));

        const fileResults =
            searchMode === 'folders'
                ? []
                : [...items, ...diaryItems].filter(item => !item.is_folder && matchesSearch(item, searchTerm));

        const merged = new Map<string, ConhecimentoItem>();
        [...folderResults, ...fileResults].forEach(item => merged.set(item.id, item));
        return sortItems(Array.from(merged.values()));
    }

    if (currentFolderId === null) {
        const roots = folderStructure
            .filter(folder => isRootKnowledgeFolderId(folder.id))
            .sort(
                (a, b) =>
                    ROOT_FOLDER_ORDER.indexOf(a.id as typeof ROOT_FOLDER_ORDER[number]) -
                    ROOT_FOLDER_ORDER.indexOf(b.id as typeof ROOT_FOLDER_ORDER[number])
            );
        return roots;
    }

    if (currentFolderId === ROOT_ACTIONS_FOLDER_ID) {
        return sortItems(
            folderStructure.filter(
                folder =>
                    folder.is_folder &&
                    folder.parent_id === ROOT_ACTIONS_FOLDER_ID &&
                    isActionVirtualFolderId(folder.id)
            )
        );
    }

    if (currentFolderId === ROOT_HEALTH_FOLDER_ID) {
        return sortItems(
            items.filter(item => classifyKnowledgeDomain(item) === 'saude' && !item.parent_id)
        );
    }

    if (currentFolderId === ROOT_PROJECTS_FOLDER_ID) {
        return sortItems(
            items.filter(item => classifyKnowledgeDomain(item) === 'projetos' && !item.parent_id)
        );
    }

    if (isActionVirtualFolderId(currentFolderId)) {
        const taskId = getTaskIdFromActionFolderId(currentFolderId);
        if (!taskId) return [];

        const actionDocs = items.filter(
            item =>
                classifyKnowledgeDomain(item) === 'acoes' &&
                item.origem?.id_origem === taskId
        );

        const task = allTasks.find(t => t.id === taskId);
        const actionItems = task ? [...actionDocs, createActionDiaryItem(task)] : actionDocs;
        return sortItems(actionItems);
    }

    return sortItems(items.filter(item => item.parent_id === currentFolderId));
}
