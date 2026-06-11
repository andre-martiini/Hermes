import React from 'react';
import { ShoppingListTool } from './ShoppingListTool';
import { TranscriptionTool } from './TranscriptionTool';
import { MeetingTranscriptionTool } from './MeetingTranscriptionTool';
import { PopManagerTool } from './PopManagerTool';
import { SipacTrackingTool } from './SipacTrackingTool';

export interface ToolParameterSchema {
    type: string;
    properties: Record<string, any>;
    required?: string[];
}

export interface ToolMetadata {
    id: string;
    ui_metadata: {
        title: string;
        description: string;
        icon: string;
        category: string;
        tag: string;
    };
    keys: string[];
    parametersSchema: ToolParameterSchema;
    component: React.ComponentType<any>;
}

export const toolsRegistry: ToolMetadata[] = [
    {
        id: 'ShoppingListTool',
        ui_metadata: {
            title: 'Lista de Compras',
            description: 'Organize suas compras com sugestões de IA.',
            icon: 'shopping',
            category: 'Pessoal',
            tag: '@ShoppingListTool'
        },
        keys: ['compras', 'lista de compras', 'mercado', 'comprar'],
        parametersSchema: {
            type: 'object',
            properties: {
                assistantAction: {
                    type: 'string',
                    description: 'Acao estruturada para a lista de compras. Use: view, create, update, delete, import_batch, clear_planning ou finalize.'
                },
                targetItemId: {
                    type: 'string',
                    description: 'ID exato do item alvo quando ele ja for conhecido.'
                },
                targetItemName: {
                    type: 'string',
                    description: 'Nome do item alvo quando o ID nao for conhecido. Use o nome mais especifico possivel.'
                },
                nome: {
                    type: 'string',
                    description: 'Nome do item a criar ou novo nome do item a alterar.'
                },
                categoria: {
                    type: 'string',
                    description: 'Categoria atualizada do item.'
                },
                quantidade: {
                    type: 'string',
                    description: 'Quantidade textual do item, por exemplo 1, 2, 0.5 ou 12.'
                },
                unit: {
                    type: 'string',
                    description: 'Unidade do item, por exemplo un, kg, L, pct.'
                },
                isPlanned: {
                    type: 'boolean',
                    description: 'Se o item deve ficar marcado para a etapa de planejamento.'
                },
                isPurchased: {
                    type: 'boolean',
                    description: 'Se o item deve ficar marcado como comprado.'
                },
                ordem: {
                    type: 'number',
                    description: 'Posicao numerica do item na lista.'
                },
                initialImportText: {
                    type: 'string',
                    description: 'Texto bruto para importacao em lote. Use uma linha por item, no formato Nome|Categoria.'
                },
                initialView: {
                    type: 'string',
                    description: 'Aba inicial da ferramenta: catalog, planning ou shopping.'
                },
                initialSearchTerm: {
                    type: 'string',
                    description: 'Filtro inicial para destacar itens relevantes na lista.'
                }
            }
        },
        component: ShoppingListTool
    },
    {
        id: 'TranscriptionTool',
        ui_metadata: {
            title: 'Transcrição de Áudio',
            description: 'Transcreva e refine áudios.',
            icon: 'transcription',
            category: 'Produtividade',
            tag: '@TranscriptionTool'
        },
        keys: ['transcrever', 'transcrição', 'áudio', 'audio', 'texto do audio'],
        parametersSchema: {
            type: 'object',
            properties: {
                initialText: {
                    type: 'string',
                    description: 'Texto opcional para inicializar a ferramenta de transcrição.'
                }
            }
        },
        component: TranscriptionTool
    },

    {
        id: 'MeetingTranscriptionTool',
        ui_metadata: {
            title: 'Transcrição de Reunião',
            description: 'Transcreva com áudio duplo e chat IA.',
            icon: 'meeting',
            category: 'Produtividade',
            tag: '@MeetingTranscriptionTool'
        },
        keys: ['reunião', 'ata', 'transcrição de reunião', 'gravação de reunião'],
        parametersSchema: {
            type: 'object',
            properties: {}
        },
        component: MeetingTranscriptionTool
    },
    {
        id: 'PopManagerTool',
        ui_metadata: {
            title: 'Gerenciador de POPs',
            description: 'Gerencie Procedimentos Operacionais Padrão.',
            icon: 'pop',
            category: 'Sistema',
            tag: '@PopManagerTool'
        },
        keys: ['pop', 'procedimento', 'procedimentos', 'operacional'],
        parametersSchema: {
            type: 'object',
            properties: {
                initialSearch: {
                    type: 'string',
                    description: 'Termo de busca inicial para POPs.'
                }
            }
        },
        component: PopManagerTool
    },
    {
        id: 'SipacTrackingTool',
        ui_metadata: {
            title: 'Acompanhamento SIPAC',
            description: 'Consulte processos públicos, andamentos e documentos anexos.',
            icon: 'sipac',
            category: 'Produtividade',
            tag: '@SipacTrackingTool'
        },
        keys: ['sipac', 'processo', 'acompanhamento sipac', 'processo sipac', 'rastrear processo'],
        parametersSchema: {
            type: 'object',
            properties: {
                initialProcesso: {
                    type: 'string',
                    description: 'O número do processo SIPAC a ser consultado inicialmente.'
                }
            }
        },
        component: SipacTrackingTool
    }
];

export const getRoutingIndex = () => {
    return toolsRegistry.map(tool => ({
        id: tool.id,
        tag: tool.ui_metadata.tag,
        keys: tool.keys,
        parametersSchema: tool.parametersSchema
    }));
};
