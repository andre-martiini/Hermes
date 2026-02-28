import { expect, test, describe } from 'vitest';
import { computeFolderStructure, filterCurrentItems } from './utils/knowledgeLogic';
import { ConhecimentoItem, Tarefa } from '../types';

describe('Knowledge Logic - Virtual Folders', () => {
    const mockTasks: Tarefa[] = [
        {
            id: 'task_with_docs',
            titulo: 'Tarefa Com Docs',
            projeto: 'p1',
            data_inicio: '2023-01-01',
            data_limite: '2023-01-02',
            status: 'A Fazer' as any,
            prioridade: 'alta',
            categoria: 'geral',
            contabilizar_meta: false,
            data_criacao: '2023-01-01'
        },
        {
            id: 'task_empty',
            titulo: 'Tarefa Vazia',
            projeto: 'p1',
            data_inicio: '2023-01-01',
            data_limite: '2023-01-02',
            status: 'A Fazer' as any,
            prioridade: 'alta',
            categoria: 'geral',
            contabilizar_meta: false,
            data_criacao: '2023-01-01'
        }
    ];

    const mockItems: ConhecimentoItem[] = [
        {
            id: 'doc_1',
            titulo: 'Doc 1.pdf',
            tipo_arquivo: 'pdf',
            url_drive: '',
            tamanho: 100,
            data_criacao: '2023-01-01',
            origem: { modulo: 'acoes', id_origem: 'task_with_docs' }
        },
        {
            id: 'folder_real',
            titulo: 'Pasta Real',
            tipo_arquivo: 'folder',
            url_drive: '',
            tamanho: 0,
            data_criacao: '2023-01-01',
            is_folder: true,
            parent_id: null
        }
    ];

    test('computeFolderStructure generates virtual folders only for tasks with docs', () => {
        const folders = computeFolderStructure(mockItems, mockTasks);

        expect(folders).toHaveLength(2); // 1 real + 1 virtual

        const virtualFolder = folders.find(f => f.id === 'task_with_docs');
        expect(virtualFolder).toBeDefined();
        expect(virtualFolder?.tipo_arquivo).toBe('virtual_folder');

        const emptyFolder = folders.find(f => f.id === 'task_empty');
        expect(emptyFolder).toBeUndefined();
    });

    test('filterCurrentItems correctly filters root items and injects virtual folders', () => {
        const folders = computeFolderStructure(mockItems, mockTasks);
        const rootItems = filterCurrentItems(mockItems, mockTasks, folders, null, '');

        // Root should show: 'folder_real' AND the virtual folder 'task_with_docs'
        // It should NOT show 'doc_1' because 'doc_1' belongs to the virtual folder
        expect(rootItems).toHaveLength(2);
        expect(rootItems.find(i => i.id === 'folder_real')).toBeDefined();
        expect(rootItems.find(i => i.id === 'task_with_docs')).toBeDefined();
        expect(rootItems.find(i => i.id === 'doc_1')).toBeUndefined();
    });

    test('filterCurrentItems correctly filters items inside a virtual folder', () => {
        const folders = computeFolderStructure(mockItems, mockTasks);
        const insideVirtualFolder = filterCurrentItems(mockItems, mockTasks, folders, 'task_with_docs', '');

        // Inside the virtual folder 'task_with_docs', it should show 'doc_1'
        expect(insideVirtualFolder).toHaveLength(1);
        expect(insideVirtualFolder[0].id).toBe('doc_1');
    });
});
