const items = [
    { id: '1', titulo: 'Root File', parent_id: null },
    { id: '2', titulo: 'Folder A', is_folder: true, parent_id: null },
    { id: '3', titulo: 'File in A', parent_id: '2' },
    { id: '4', titulo: 'Folder B', is_folder: true, parent_id: '2' },
    { id: '5', titulo: 'File in B', parent_id: '4' }
];

const getItemsInFolder = (items, folderId) => {
    return items.filter(item => {
        if (folderId === null) return !item.parent_id;
        return item.parent_id === folderId;
    });
};

const rootItems = getItemsInFolder(items, null);
if (rootItems.length === 2 && rootItems.some(i => i.id === '1') && rootItems.some(i => i.id === '2')) {
    console.log('PASS: Root items');
} else {
    console.error('FAIL: Root items', rootItems);
    process.exit(1);
}

const folderAItems = getItemsInFolder(items, '2');
if (folderAItems.length === 2 && folderAItems.some(i => i.id === '3') && folderAItems.some(i => i.id === '4')) {
    console.log('PASS: Folder A items');
} else {
    console.error('FAIL: Folder A items', folderAItems);
    process.exit(1);
}

const folderBItems = getItemsInFolder(items, '4');
if (folderBItems.length === 1 && folderBItems[0].id === '5') {
    console.log('PASS: Folder B items');
} else {
    console.error('FAIL: Folder B items', folderBItems);
    process.exit(1);
}
