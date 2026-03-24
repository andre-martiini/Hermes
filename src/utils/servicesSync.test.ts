import { describe, it, expect } from 'vitest';
import { syncServiceToFinance } from './servicesSync';
import { Servico, IncomeEntry } from '../../types';

describe('syncServiceToFinance', () => {
    it('should add new entries for an active service with pending milestones', () => {
        const servico: Servico = {
            id: 'serv1',
            titulo: 'Website Redesign',
            descricao: 'Redesign of corporate website',
            cliente: 'Acme Corp',
            papel: 'Desenvolvedor Frontend',
            status: 'Ativo',
            tags: ['React', 'Tailwind'],
            data_inicio: '2024-01-01',
            data_termino: '2024-03-01',
            carga_horaria_semanal: 20,
            tipo_contrato: 'Pacote Fechado',
            valor_total: 5000,
            parcelas: [
                {
                    id: 'parc1',
                    valor: 2500,
                    data_prevista: '2024-01-15T00:00:00Z',
                    status: 'pendente',
                    descricao: 'Entrada 50%'
                }
            ],
            data_criacao: '2024-01-01',
            data_atualizacao: '2024-01-01'
        };

        const result = syncServiceToFinance(servico, [], 0, 2024);

        expect(result.entriesToAdd).toHaveLength(1);
        expect(result.entriesToUpdate).toHaveLength(0);

        const addedEntry = result.entriesToAdd[0];
        expect(addedEntry.amount).toBe(2500);
        expect(addedEntry.description).toBe('[Serviço: Website Redesign] Entrada 50%');
        expect(addedEntry.isReceived).toBe(false);
        expect(addedEntry.rubricId).toBe('parc1');
    });

    it('should update existing entries when milestone values change', () => {
        const servico: Servico = {
            id: 'serv1',
            titulo: 'App Development',
            descricao: 'Mobile app creation',
            cliente: 'Startup Inc',
            papel: 'Fullstack Dev',
            status: 'Ativo',
            tags: ['React Native'],
            data_inicio: '2024-02-01',
            data_termino: '2024-05-01',
            carga_horaria_semanal: 30,
            tipo_contrato: 'Mensalidade',
            valor_total: 10000,
            parcelas: [
                {
                    id: 'parc1',
                    valor: 3500, // Updated value
                    data_prevista: '2024-02-28T00:00:00Z',
                    status: 'pago', // Updated status
                    descricao: 'Fevereiro'
                }
            ],
            data_criacao: '2024-01-01',
            data_atualizacao: '2024-02-15'
        };

        const existingEntries: IncomeEntry[] = [
            {
                id: 'entry1',
                description: '[Serviço: App Development] Fevereiro',
                amount: 3000, // Old value
                day: 28,
                month: 1,
                year: 2024,
                category: 'Renda de Serviços',
                isReceived: false, // Old status
                rubricId: 'parc1'
            }
        ];

        const result = syncServiceToFinance(servico, existingEntries, 1, 2024);

        expect(result.entriesToAdd).toHaveLength(0);
        expect(result.entriesToUpdate).toHaveLength(1);

        const updatedEntry = result.entriesToUpdate[0];
        expect(updatedEntry.amount).toBe(3500);
        expect(updatedEntry.isReceived).toBe(true);
        expect(updatedEntry.id).toBe('entry1');
    });

    it('should not process cancelled or prospecting services', () => {
        const servico: Servico = {
            id: 'serv1',
            titulo: 'SEO Optimization',
            descricao: 'SEO audit and improvements',
            cliente: 'Local Shop',
            papel: 'Consultor',
            status: 'Prospecção',
            tags: ['SEO'],
            data_inicio: '2024-04-01',
            data_termino: '2024-04-30',
            carga_horaria_semanal: 10,
            tipo_contrato: 'Pacote Fechado',
            valor_total: 1500,
            parcelas: [
                {
                    id: 'parc1',
                    valor: 1500,
                    data_prevista: '2024-04-15T00:00:00Z',
                    status: 'pendente',
                    descricao: 'Pagamento Único'
                }
            ],
            data_criacao: '2024-03-01',
            data_atualizacao: '2024-03-01'
        };

        const result = syncServiceToFinance(servico, [], 3, 2024);

        expect(result.entriesToAdd).toHaveLength(0);
        expect(result.entriesToUpdate).toHaveLength(0);
    });
});
