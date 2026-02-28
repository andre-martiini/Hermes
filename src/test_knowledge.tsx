import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import KnowledgeView from '../KnowledgeView';
import { ConhecimentoItem, Tarefa } from '../types';

const mockTasks: Tarefa[] = [
    {
        id: 'task_1',
        titulo: 'Ação com Documentos',
        projeto: 'proj_1',
        data_inicio: new Date().toISOString(),
        data_limite: new Date().toISOString(),
        status: 'A Fazer' as any,
        prioridade: 'alta',
        categoria: 'geral',
        contabilizar_meta: false,
        data_criacao: new Date().toISOString()
    },
    {
        id: 'task_2',
        titulo: 'Ação Vazia',
        projeto: 'proj_1',
        data_inicio: new Date().toISOString(),
        data_limite: new Date().toISOString(),
        status: 'pendente',
        prioridade: 'alta',
        categoria: 'geral',
        contabilizar_meta: false,
        data_criacao: new Date().toISOString()
    }
];

const mockItems: ConhecimentoItem[] = [
    {
        id: 'doc_1',
        titulo: 'Documento da Ação.pdf',
        tipo_arquivo: 'pdf',
        url_drive: 'https://example.com/doc.pdf',
        tamanho: 1024,
        data_criacao: new Date().toISOString(),
        is_folder: false,
        origem: { modulo: 'acoes', id_origem: 'task_1' }
    },
    {
        id: 'folder_1',
        titulo: 'Pasta Real',
        tipo_arquivo: 'folder',
        url_drive: '',
        tamanho: 0,
        data_criacao: new Date().toISOString(),
        is_folder: true,
        parent_id: null
    },
    {
        id: 'img_1',
        titulo: 'Imagem na Raiz.jpg',
        tipo_arquivo: 'imagem',
        url_drive: 'https://example.com/img.jpg',
        tamanho: 512,
        data_criacao: new Date().toISOString(),
        is_folder: false,
        parent_id: null
    }
];

const TestApp = () => {
    const [items, setItems] = useState<ConhecimentoItem[]>(mockItems);

    const handleSaveItem = async (item: Partial<ConhecimentoItem>) => {
        setItems(prev => {
            const existing = prev.find(i => i.id === item.id);
            if (existing) {
                return prev.map(i => i.id === item.id ? { ...i, ...item } as ConhecimentoItem : i);
            }
            return [...prev, item as ConhecimentoItem];
        });
    };

    const handleDeleteItem = (id: string) => {
        setItems(prev => prev.filter(i => i.id !== id));
    };

    return (
        <div className="p-8 h-screen bg-slate-900">
            <KnowledgeView
                items={items}
                allTasks={mockTasks}
                onSaveItem={handleSaveItem}
                onDeleteItem={handleDeleteItem}
                onUploadFile={() => {}}
                onAddLink={async () => {}}
                showConfirm={(title, message, onConfirm) => {
                    if (window.confirm(`${title}\n${message}`)) onConfirm();
                }}
            />
        </div>
    );
};

const root = createRoot(document.getElementById('root')!);
root.render(<TestApp />);
