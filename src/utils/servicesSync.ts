import { Servico, IncomeEntry } from '../types';

/**
 * Synchronizes the milestones (parcelas) of a given Servico with the financial system.
 * It will determine which IncomeEntries need to be added, updated, or if there's
 * no action needed.
 *
 * Returns an array of operations to perform on the database to keep it in sync.
 */
export const syncServiceToFinance = (
    servico: Servico,
    currentEntries: IncomeEntry[],
    currentMonth: number,
    currentYear: number
): {
    entriesToAdd: Omit<IncomeEntry, 'id'>[];
    entriesToUpdate: IncomeEntry[];
} => {
    const entriesToAdd: Omit<IncomeEntry, 'id'>[] = [];
    const entriesToUpdate: IncomeEntry[] = [];

    // Only process 'Ativo' or 'Concluído' services.
    if (servico.status !== 'Ativo' && servico.status !== 'Concluído') {
        return { entriesToAdd, entriesToUpdate };
    }

    const servicePrefix = `[Serviço: ${servico.titulo}]`;

    servico.parcelas.forEach(parcela => {
        // Find existing entry linked to this parcela
        const existingEntry = currentEntries.find(e => e.rubricId === parcela.id);

        // Parse expected date
        let month = currentMonth;
        let year = currentYear;
        let day = new Date().getDate();

        if (parcela.data_prevista) {
            const dateObj = new Date(parcela.data_prevista);
            if (!isNaN(dateObj.getTime())) {
                month = dateObj.getMonth();
                year = dateObj.getFullYear();
                day = dateObj.getDate();
            }
        }

        const expectedDescription = `${servicePrefix} ${parcela.descricao || 'Parcela'}`;

        if (existingEntry) {
            // Check if updates are needed
            if (
                existingEntry.amount !== parcela.valor ||
                existingEntry.day !== day ||
                existingEntry.month !== month ||
                existingEntry.year !== year ||
                existingEntry.description !== expectedDescription ||
                existingEntry.isReceived !== (parcela.status === 'pago')
            ) {
                entriesToUpdate.push({
                    ...existingEntry,
                    amount: parcela.valor,
                    day: day,
                    month: month,
                    year: year,
                    description: expectedDescription,
                    isReceived: parcela.status === 'pago'
                });
            }
        } else {
            // Needs to be added
            entriesToAdd.push({
                description: expectedDescription,
                amount: parcela.valor,
                day: day,
                month: month,
                year: year,
                category: 'Renda de Serviços', // Custom category for services
                isReceived: parcela.status === 'pago',
                rubricId: parcela.id
            });
        }
    });

    return { entriesToAdd, entriesToUpdate };
};
