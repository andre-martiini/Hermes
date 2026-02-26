
const items = [
    { id: '1', titulo: 'Doc 1', categoria: 'Geral', data_criacao: '2023-01-01' },
    { id: '2', titulo: 'Task Doc', categoria: 'Geral', origem: { modulo: 'tarefas' }, data_criacao: '2023-01-02' },
    { id: '3', titulo: 'Another Doc', categoria: 'Financeiro', data_criacao: '2023-01-03' }
];

const filterItems = (items, category) => {
    return items.filter(item => {
        let matchesCategory = true;
        if (category === 'Ações') {
            matchesCategory = item.origem?.modulo === 'tarefas';
        } else if (category) {
            matchesCategory = item.categoria === category;
        }
        return matchesCategory;
    });
};

const actions = filterItems(items, 'Ações');
if (actions.length === 1 && actions[0].id === '2') {
    console.log('PASS: Filter by Ações');
} else {
    console.error('FAIL: Filter by Ações', actions);
    process.exit(1);
}

const fin = filterItems(items, 'Financeiro');
if (fin.length === 1 && fin[0].id === '3') {
    console.log('PASS: Filter by Category');
} else {
    console.error('FAIL: Filter by Category', fin);
    process.exit(1);
}
