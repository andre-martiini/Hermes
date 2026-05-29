self.importScripts('https://cdn.jsdelivr.net/npm/idb-keyval@6.2.1/dist/umd.js');

const EXPONENTIAL_BACKOFF_BASE = 5000;
const MAX_RETRIES = 5;

// Fila na memória para o retry simple. (Num caso real complexo usaríamos IndexedDB para a fila tbm)
const queue = [];

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'START_MOBILE_MEETING_UPLOAD') {
    const { storagePath, idbKey, startedAt, endedAt, title, uploadUrl, token, projectId } = event.data;
    const task = { storagePath, idbKey, startedAt, endedAt, title, uploadUrl, token, projectId, attempt: 1 };
    processTask(task);
  }
});

async function processTask(task) {
  console.log(`[SW] Iniciando upload mobile (tentativa ${task.attempt}) para ${task.idbKey}`);
  try {
    // 1. Read file from IndexedDB
    const fileData = await idbKeyval.get(task.idbKey);
    if (!fileData) {
      console.error(`[SW] File not found in IndexedDB for key: ${task.idbKey}`);
      return;
    }

    // 2. Check battery (Optimistic Approach)
    if ('getBattery' in navigator) {
      try {
        const battery = await navigator.getBattery();
        if (battery.level < 0.15 && !battery.charging) {
          console.warn('[SW] Battery low and not charging. Will still attempt upload (optimistic).');
        }
      } catch (err) {
         console.warn('[SW] Battery API error, proceeding anyway.', err);
      }
    }

    // 3. Upload to Firebase Storage using Google Cloud Storage REST API for uploads
    // https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o?uploadType=media&name={object_path}
    const bucket = `${task.projectId}.appspot.com`; // default bucket
    const objectName = encodeURIComponent(task.storagePath.replace(`gs://${bucket}/`, ''));
    const url = `https://storage.googleapis.com/upload/storage/v1/b/${bucket}/o?uploadType=media&name=${objectName}`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${task.token}`,
        'Content-Type': 'audio/ogg',
      },
      body: fileData
    });

    if (!response.ok) {
      throw new Error(`Storage upload failed with status ${response.status}: ${await response.text()}`);
    }

    console.log(`[SW] Upload finalizado para o Storage. Chamando Cloud Function de transcrição.`);

    // 4. Call Cloud Function
    // We construct the function URL
    const functionUrl = `https://us-central1-${task.projectId}.cloudfunctions.net/transcrever_reuniao_mobile`;

    const funcResponse = await fetch(functionUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${task.token}`
      },
      body: JSON.stringify({
        data: {
          storage_path: `gs://${bucket}/${decodeURIComponent(objectName)}`,
          startedAt: task.startedAt,
          endedAt: task.endedAt,
          title: task.title
        }
      })
    });

    if (!funcResponse.ok) {
        throw new Error(`Function call failed with status ${funcResponse.status}`);
    }

    console.log(`[SW] Cloud Function chamada com sucesso! Transcrição na nuvem iniciada.`);

    // Note: The audio chunk in IndexedDB is kept until the frontend deletes it based on 'visualizado: true'.

  } catch (error) {
    console.error(`[SW] Erro no upload (tentativa ${task.attempt}):`, error);
    if (task.attempt < MAX_RETRIES) {
      const delay = EXPONENTIAL_BACKOFF_BASE * Math.pow(2, task.attempt - 1);
      console.log(`[SW] Agendando retry em ${delay}ms...`);
      task.attempt++;
      setTimeout(() => processTask(task), delay);
    } else {
      console.error(`[SW] Falha final após ${MAX_RETRIES} tentativas.`);
    }
  }
}
