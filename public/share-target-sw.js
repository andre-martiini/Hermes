self.addEventListener('fetch', (event) => {
  if (event.request.method === 'POST' && event.request.url.includes('/_share-target')) {
    event.respondWith(
      (async () => {
        try {
          const formData = await event.request.formData();
          const audioFile = formData.get('audioFile');
          const videoFile = formData.get('videoFile');
          
          const title = formData.get('title') || '';
          const text = formData.get('text') || '';
          
          const filesToStore = [];
          if (audioFile && audioFile.size > 0) filesToStore.push({ file: audioFile, type: 'audio' });
          if (videoFile && videoFile.size > 0) filesToStore.push({ file: videoFile, type: 'video' });
          // Mensagem de texto compartilhada sem arquivo (ex: texto do WhatsApp) também entra na fila do lote.
          if (filesToStore.length === 0 && ((text && text.trim()) || (title && title.trim()))) {
            filesToStore.push({ file: null, type: 'text' });
          }
          
          // Abre o IndexedDB
          const openRequest = indexedDB.open('hermes-share-db', 1);
          
          await new Promise((resolve, reject) => {
            openRequest.onupgradeneeded = (e) => {
              const db = e.target.result;
              if (!db.objectStoreNames.contains('shared-files')) {
                db.createObjectStore('shared-files', { keyPath: 'id', autoIncrement: true });
              }
            };
            openRequest.onsuccess = () => resolve(openRequest.result);
            openRequest.onerror = () => reject('Erro ao abrir DB');
          });
          
          const db = openRequest.result;
          const transaction = db.transaction('shared-files', 'readwrite');
          const store = transaction.objectStore('shared-files');
          
          for (const item of filesToStore) {
            store.add({
              file: item.file,
              fileType: item.type,
              title: title,
              text: text,
              timestamp: Date.now()
            });
          }
          
          await new Promise((resolve, reject) => {
            transaction.oncomplete = () => resolve();
            transaction.onerror = () => reject('Erro ao salvar no DB');
          });
          
          // Redireciona de volta pro app com a flag ?sharedIntent=true
          return Response.redirect('/?sharedIntent=true', 303);
          
        } catch (err) {
          console.error('[ShareTargetSW] Erro ao processar:', err);
          return Response.redirect('/?sharedIntentError=true', 303);
        }
      })()
    );
  }
});
