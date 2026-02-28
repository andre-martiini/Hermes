import { ConhecimentoItem, Tarefa } from '../../types';

export function computeFolderStructure(items: ConhecimentoItem[], allTasks: Tarefa[]) {
    const realFolders = items.filter(i => i.is_folder);

    const tasksWithDocs = allTasks.filter(task =>
        items.some(item => item.origem?.modulo === 'acoes' && item.origem?.id_origem === task.id)
    );

    const virtualTaskFolders = tasksWithDocs.map(task => ({
        id: task.id,
        titulo: task.titulo,
        is_folder: true,
        tipo_arquivo: 'virtual_folder',
        data_criacao: task.data_criacao,
        tamanho: 0,
        url_drive: '',
        parent_id: null
    } as ConhecimentoItem));

    return [...realFolders, ...virtualTaskFolders];
}

export function filterCurrentItems(items: ConhecimentoItem[], allTasks: Tarefa[], folderStructure: ConhecimentoItem[], currentFolderId: string | null, searchTerm: string) {
    let filtered = items.filter(item => {
        // For virtual task folders, display items linked to that task's action
        if (currentFolderId && allTasks.some(t => t.id === currentFolderId)) {
            return item.origem?.modulo === 'acoes' && item.origem?.id_origem === currentFolderId;
        }

        // If searching, show all matching items regardless of folder
        if (searchTerm) {
            const lowerSearch = searchTerm.toLowerCase();
            return (
                item.titulo.toLowerCase().includes(lowerSearch) ||
                (item.tags && item.tags.some(tag => tag.toLowerCase().includes(lowerSearch))) ||
                (item.texto_bruto && item.texto_bruto.toLowerCase().includes(lowerSearch))
            );
        }

        // Otherwise show items in current folder
        if (currentFolderId === null) {
            // Return real root items (no parent, and not linked to any action task)
            return !item.parent_id && item.origem?.modulo !== 'acoes';
        }
        return item.parent_id === currentFolderId;
    });

    // Inject the generated virtual folders into the root view
    if (currentFolderId === null && !searchTerm) {
        const virtualTaskFolders = folderStructure.filter(f => f.tipo_arquivo === 'virtual_folder');
        filtered = [...filtered, ...virtualTaskFolders];
    }

    // Sort: Folders first, then files by date
    return filtered.sort((a, b) => {
        if (a.is_folder && !b.is_folder) return -1;
        if (!a.is_folder && b.is_folder) return 1;
        return new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime();
    });
}
