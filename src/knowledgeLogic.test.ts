import { expect, test, describe } from 'vitest';
import {
    ROOT_ACTIONS_FOLDER_ID,
    ROOT_HEALTH_FOLDER_ID,
    ROOT_PROJECTS_FOLDER_ID,
    computeFolderStructure,
    filterCurrentItems,
    getActionVirtualFolderId
} from './utils/knowledgeLogic';
import { ConhecimentoItem, Tarefa } from '../types';

describe('Knowledge Logic - Top Folders and Action Subfolders', () => {
    const mockTasks: Tarefa[] = [
        {
            id: 'task_with_docs',
            titulo: 'Ação Com Docs',
            projeto: 'p1',
            data_inicio: '2023-01-01',
            data_limite: '2023-01-02',
            status: 'A Fazer' as any,
            prioridade: 'alta',
            categoria: 'geral',
            contabilizar_meta: false,
            data_criacao: '2023-01-01',
            acompanhamento: [{ data: '2023-01-01T10:00:00.000Z', nota: 'Primeiro registro' }]
        },
        {
            id: 'task_empty',
            titulo: 'Ação Sem Docs',
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
            titulo: 'Doc da ação.pdf',
            tipo_arquivo: 'pdf',
            url_drive: 'https://example.com/doc.pdf',
            tamanho: 100,
            data_criacao: '2023-01-01',
            origem: { modulo: 'tarefas', id_origem: 'task_with_docs' }
        },
        {
            id: 'health_1',
            titulo: 'Exame sangue.pdf',
            tipo_arquivo: 'pdf',
            url_drive: 'https://example.com/health.pdf',
            tamanho: 120,
            data_criacao: '2023-01-01',
            origem: { modulo: 'saude', id_origem: 'exam-1' }
        }
    ];

    test('computeFolderStructure always returns root folders and action subfolders with docs', () => {
        const folders = computeFolderStructure(mockItems, mockTasks);

        expect(folders.find(f => f.id === ROOT_ACTIONS_FOLDER_ID)).toBeDefined();
        expect(folders.find(f => f.id === ROOT_HEALTH_FOLDER_ID)).toBeDefined();
        expect(folders.find(f => f.id === ROOT_PROJECTS_FOLDER_ID)).toBeDefined();
        expect(folders.find(f => f.id === getActionVirtualFolderId('task_with_docs'))).toBeDefined();
        expect(folders.find(f => f.id === getActionVirtualFolderId('task_empty'))).toBeUndefined();
    });

    test('root view shows only top folders', () => {
        const folders = computeFolderStructure(mockItems, mockTasks);
        const rootItems = filterCurrentItems(mockItems, mockTasks, folders, null, '');

        expect(rootItems).toHaveLength(3);
        expect(rootItems.map(i => i.id)).toEqual([
            ROOT_ACTIONS_FOLDER_ID,
            ROOT_HEALTH_FOLDER_ID,
            ROOT_PROJECTS_FOLDER_ID
        ]);
    });

    test('actions folder lists action subfolders, not raw files', () => {
        const folders = computeFolderStructure(mockItems, mockTasks);
        const actionRootItems = filterCurrentItems(mockItems, mockTasks, folders, ROOT_ACTIONS_FOLDER_ID, '');

        expect(actionRootItems).toHaveLength(1);
        expect(actionRootItems[0].id).toBe(getActionVirtualFolderId('task_with_docs'));
    });

    test('inside action subfolder shows linked documents and generated diary txt', () => {
        const folders = computeFolderStructure(mockItems, mockTasks);
        const actionItems = filterCurrentItems(
            mockItems,
            mockTasks,
            folders,
            getActionVirtualFolderId('task_with_docs'),
            ''
        );

        expect(actionItems.find(i => i.id === 'doc_1')).toBeDefined();
        expect(actionItems.find(i => i.titulo.endsWith('.txt'))).toBeDefined();
    });

    test('orphan action folder uses custom persisted title when available', () => {
        const orphanItems: ConhecimentoItem[] = [
            {
                id: 'orphan_doc',
                titulo: 'Orphan Doc.pdf',
                tipo_arquivo: 'pdf',
                url_drive: 'https://example.com/orphan.pdf',
                tamanho: 50,
                data_criacao: '2023-01-01',
                origem: { modulo: 'tarefas', id_origem: 'orphan_task_1' },
                orphan_action_title: 'Ação Renomeada Manualmente'
            }
        ];

        const folders = computeFolderStructure(orphanItems, mockTasks);
        const orphanFolder = folders.find(f => f.id === getActionVirtualFolderId('orphan_task_1'));

        expect(orphanFolder).toBeDefined();
        expect(orphanFolder?.titulo).toBe('Ação Renomeada Manualmente');
    });
});
