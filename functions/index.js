/**
 * Firebase Cloud Function para sincronização Hermes <-> Google Tasks
 * 
 * Esta função:
 * 1. Monitora mudanças no documento system/sync
 * 2. Quando status = 'requested', executa a sincronização
 * 3. Usa as credenciais OAuth armazenadas no Firestore
 * 4. Sincroniza bidirecional (PUSH + PULL)
 */

const functions = require('firebase-functions');
const admin = require('firebase-admin');
const { google } = require('googleapis');

admin.initializeApp();
const db = admin.firestore();

/**
 * Classifica a tarefa com base em tags
 */
function classifyTask(title, notes = '') {
    const text = `${title} ${notes}`.toUpperCase();

    let categoria = 'NÃO CLASSIFICADA';
    let contabilizarMeta = false;

    // Regex para encontrar tags
    const tagMatches = text.match(/\[(.*?)\]|TAG:\s*([\w\-]+)/g) || [];
    const tags = tagMatches.map(t =>
        t.replace(/[\[\]]/g, '').replace(/TAG:\s*/i, '').toUpperCase()
    );

    if (tags.some(tag => ['CLC', 'LICITACAO'].includes(tag))) {
        categoria = 'CLC';
        contabilizarMeta = true;
    } else if (tags.some(tag => ['ASSISTENCIA', 'ESTUDANTIL', 'ASSISTENCIA-ESTUDANTIL'].includes(tag))) {
        categoria = 'ASSISTÊNCIA';
        contabilizarMeta = true;
    } else if (tags.includes('GERAL')) {
        categoria = 'GERAL';
    }

    return { categoria, contabilizarMeta };
}

/**
 * Encontra a lista de tarefas correta com fallback
 */
function findTaskList(items) {
    if (!items || items.length === 0) return null;

    // 1. Tenta encontrar "Tarefas gerais" (ou variações)
    const target = items.find(i => {
        const t = i.title.toLowerCase();
        return t === 'tarefas gerais' || t === 'tarefa gerais' || t === 'tarefas-gerais';
    });
    if (target) return target;

    // 2. Tenta "Tarefas" (Padrão PT-BR)
    const tarefas = items.find(i => i.title === 'Tarefas');
    if (tarefas) return tarefas;

    // 3. Tenta "My Tasks" (Padrão EN)
    const myTasks = items.find(i => i.title === 'My Tasks' || i.title === 'Tasks');
    if (myTasks) return myTasks;

    // 4. Retorna a primeira lista encontrada (Fallback final)
    return items[0];
}

/**
 * Obtém o serviço do Google Tasks usando credenciais do Firestore
 */
async function getTasksService() {
    const credsDoc = await db.collection('system').doc('google_credentials').get();

    if (!credsDoc.exists) {
        throw new Error('Credenciais do Google não encontradas no Firestore');
    }

    const credsData = credsDoc.data();

    const oauth2Client = new google.auth.OAuth2(
        credsData.client_id,
        credsData.client_secret,
        'http://localhost'
    );

    oauth2Client.setCredentials({
        access_token: credsData.token,
        refresh_token: credsData.refresh_token,
        token_type: 'Bearer',
        expiry_date: credsData.expiry_date
    });

    // Atualiza o token se necessário
    oauth2Client.on('tokens', async (tokens) => {
        if (tokens.refresh_token) {
            await db.collection('system').doc('google_credentials').update({
                token: tokens.access_token,
                refresh_token: tokens.refresh_token,
                expiry_date: tokens.expiry_date
            });
        }
    });

    return google.tasks({ version: 'v1', auth: oauth2Client });
}

/**
 * PULL: Importa tarefas do Google Tasks para o Firestore
 */
async function pullFromGoogle(tasksService, logs) {
    const addLog = (msg) => {
        const timestamp = new Date().toLocaleTimeString('pt-BR');
        logs.push(`[${timestamp}] ${msg}`);
        console.log(msg);
    };

    try {
        // Busca a lista de tarefas
        const listsResponse = await tasksService.tasklists.list();
        const tasklists = listsResponse.data.items || [];

        const targetList = findTaskList(tasklists);

        if (!targetList) {
            addLog(`ERRO: Nenhuma lista de tarefas encontrada no Google Tasks. (Listas disponíveis: ${tasklists.map(t => t.title).join(', ')})`);
            return;
        }

        const tasklistId = targetList.id;
        addLog(`Usando lista: "${targetList.title}"`);

        // Busca todas as tarefas
        const gTasks = [];
        let pageToken = null;

        do {
            const response = await tasksService.tasks.list({
                tasklist: tasklistId,
                showCompleted: true,
                showHidden: true,
                maxResults: 100,
                pageToken: pageToken
            });

            gTasks.push(...(response.data.items || []));
            pageToken = response.data.nextPageToken;

            if (gTasks.length >= 200) break;
        } while (pageToken);

        addLog(`Total de ${gTasks.length} tarefas encontradas no Google`);

        // Carrega tarefas locais
        const localSnapshot = await db.collection('tarefas').get();
        const localTasks = new Map();

        localSnapshot.forEach(doc => {
            const data = doc.data();
            const googleId = data.google_id;
            if (googleId) {
                localTasks.set(googleId, { id: doc.id, data });
            } else {
                localTasks.set(`title_${data.titulo}`, { id: doc.id, data });
            }
        });

        // Processa cada tarefa do Google
        let imported = 0, updated = 0, linked = 0;

        for (const gt of gTasks) {
            const gId = gt.id;
            const title = gt.title || '(Sem Título)';

            // DEBUG: Diagnóstico de Gasto Semanal
            // DEBUG: Diagnóstico de Gasto Semanal
            if (title.toUpperCase().includes('GASTO')) {
                const exD = localTasks.get(gt.id) || localTasks.get(`title_${title}`);
                const nT = (gt.notes || '').replace(/\n/g, ' ').substring(0, 100);
                const nL = exD ? (exD.data.notas || '').replace(/\n/g, ' ').substring(0, 100) : 'N/A';
                const gD = gt.updated;
                const lD = exD ? exD.data.data_atualizacao : 'N/A';
                addLog(`DEBUG ${title.substring(0, 20)} | Notas[G:"${nT}" L:"${nL}"]`);
                if (exD && nT !== nL) {
                    addLog('DEBUG STATUS: DIFERENTES (Deveria atualizar)');
                } else if (exD) {
                    addLog('DEBUG STATUS: IGUAIS (Ignorando update)');
                }
            }

            const gUpdated = gt.updated || '';
            const due = gt.due;
            const deadline = due ? due.split('T')[0] : '-';
            const hStatus = gt.status === 'completed' ? 'concluído' : 'em andamento';

            const { categoria, contabilizarMeta } = classifyTask(title, gt.notes);

            const existing = localTasks.get(gId) || localTasks.get(`title_${title}`);

            if (existing) {
                const { id: docId, data: tOld } = existing;

                // Vincula se não tem google_id
                if (!tOld.google_id) {
                    await db.collection('tarefas').doc(docId).update({
                        google_id: gId,
                        data_atualizacao: gUpdated,
                        notas: gt.notes || '' // Garante notas ao vincular
                    });
                    linked++;
                    continue;
                }

                // Verifica discrepância de notas (Robustez)
                const gNotes = (gt.notes || '').trim();
                const lNotes = (tOld.notas || '').trim();
                const notesChanged = gNotes !== lNotes;

                // Atualiza se o Google for mais recente
                const hUpdated = tOld.data_atualizacao || '';

                // Pula se local for mais recente E notas não mudaram
                if (hUpdated && gUpdated && hUpdated >= gUpdated && !notesChanged) {
                    continue;
                }

                const hasChanged = (
                    tOld.status !== hStatus ||
                    tOld.titulo !== title ||
                    tOld.data_conclusao !== gt.completed ||
                    tOld.data_limite !== deadline ||
                    notesChanged
                );

                if (hasChanged) {
                    await db.collection('tarefas').doc(docId).update({
                        titulo: title,
                        data_limite: deadline,
                        status: hStatus,
                        data_conclusao: gt.completed || null,
                        data_atualizacao: gUpdated,
                        notas: gt.notes || '' // Garantir que notas sejam atualizadas
                    });
                    updated++;
                }
            } else {
                // Cria nova tarefa
                await db.collection('tarefas').add({
                    titulo: title,
                    projeto: 'GOOGLE',
                    data_limite: deadline,
                    google_id: gId,
                    status: hStatus,
                    data_criacao: new Date().toISOString(),
                    data_conclusao: gt.completed || null,
                    data_atualizacao: gUpdated,
                    categoria: categoria,
                    contabilizar_meta: contabilizarMeta,
                    notas: gt.notes || ''
                });
                imported++;
            }
        }

        addLog(`PULL CONCLUÍDO: ${imported} importadas, ${updated} atualizadas, ${linked} vinculadas`);
    } catch (error) {
        addLog(`ERRO PULL: ${error.message}`);
        throw error;
    }
}

/**
 * PUSH: Envia tarefas do Firestore para o Google Tasks
 */
async function pushToGoogle(tasksService, logs) {
    const addLog = (msg) => {
        const timestamp = new Date().toLocaleTimeString('pt-BR');
        logs.push(`[${timestamp}] ${msg}`);
        console.log(msg);
    };

    try {
        // Busca a lista de tarefas
        const listsResponse = await tasksService.tasklists.list();
        const tasklists = listsResponse.data.items || [];

        const targetList = findTaskList(tasklists);

        if (!targetList) {
            addLog(`ERRO: Nenhuma lista de tarefas encontrada. (Listas disponíveis: ${tasklists.map(t => t.title).join(', ')})`);
            return;
        }

        const tasklistId = targetList.id;
        addLog(`Usando lista destino: "${targetList.title}"`);

        // Busca tarefas do Google
        const gResponse = await tasksService.tasks.list({
            tasklist: tasklistId,
            showCompleted: true,
            showHidden: true,
            maxResults: 100
        });

        const gTasksMap = new Map();
        (gResponse.data.items || []).forEach(item => {
            gTasksMap.set(item.id, item);
        });

        // Busca tarefas do Firestore
        const snapshot = await db.collection('tarefas').get();

        let created = 0, updated = 0, deleted = 0;

        for (const doc of snapshot.docs) {
            const t = doc.data();
            const gId = t.google_id;
            const hStatus = t.status;

            // Remove tarefas excluídas
            if (hStatus === 'excluído') {
                if (gId) {
                    try {
                        await tasksService.tasks.delete({
                            tasklist: tasklistId,
                            task: gId
                        });
                        deleted++;
                    } catch (e) {
                        // Tarefa já foi deletada
                    }
                }
                await doc.ref.delete();
                continue;
            }

            const dueDate = (t.data_limite && t.data_limite !== '-')
                ? `${t.data_limite}T00:00:00Z`
                : null;
            const gStatus = t.status === 'concluído' ? 'completed' : 'needsAction';

            // Cria nova tarefa no Google
            if (!gId) {
                const newTask = await tasksService.tasks.insert({
                    tasklist: tasklistId,
                    requestBody: {
                        title: t.titulo,
                        notes: t.notas || '',
                        status: gStatus,
                        due: dueDate
                    }
                });

                await doc.ref.update({
                    google_id: newTask.data.id,
                    data_atualizacao: newTask.data.updated
                });
                created++;
                continue;
            }

            // Atualiza tarefa existente
            const gTask = gTasksMap.get(gId);
            if (gTask && t.data_atualizacao && t.data_atualizacao > gTask.updated) {
                await tasksService.tasks.update({
                    tasklist: tasklistId,
                    task: gId,
                    requestBody: {
                        id: gId,
                        title: t.titulo,
                        notes: t.notas || '',
                        status: gStatus,
                        due: dueDate
                    }
                });
                updated++;
            }
        }

        addLog(`PUSH FINALIZADO: ${created} criadas, ${updated} atualizadas, ${deleted} removidas`);
    } catch (error) {
        addLog(`ERRO PUSH: ${error.message}`);
        throw error;
    }
}

/**
 * Cloud Function disparada quando system/sync é atualizado
 */
exports.syncGoogleTasks = functions.firestore
    .document('system/sync')
    .onUpdate(async (change, context) => {
        const newData = change.after.data();
        const oldData = change.before.data();

        // Só processa se mudou para 'requested'
        if (newData.status !== 'requested' || oldData.status === 'requested') {
            return null;
        }

        console.log('🔄 Sincronização solicitada via Cloud Function');

        const syncRef = db.collection('system').doc('sync');
        const logs = ['Iniciando sincronização via Cloud Function...'];

        try {
            // Atualiza status para processing
            await syncRef.update({
                status: 'processing',
                logs: logs
            });

            // Obtém serviço do Google Tasks
            const tasksService = await getTasksService();

            // Executa PUSH
            await pushToGoogle(tasksService, logs);

            // Executa PULL
            await pullFromGoogle(tasksService, logs);

            // Finaliza com sucesso
            await syncRef.update({
                status: 'completed',
                last_success: new Date().toISOString(),
                logs: logs
            });

            console.log('✅ Sincronização concluída com sucesso');

        } catch (error) {
            console.error('❌ Erro na sincronização:', error);
            logs.push(`ERRO FATAL: ${error.message}`);

            await syncRef.update({
                status: 'error',
                error_message: error.message,
                logs: logs
            });
        }

        return null;
    });

/**
 * Cloud Function agendada para sincronização periódica (a cada 30 minutos)
 */
exports.scheduledSync = functions.pubsub
    .schedule('every 30 minutes')
    .onRun(async (context) => {
        console.log('⏰ Sincronização agendada iniciada');

        const syncRef = db.collection('system').doc('sync');

        // Dispara a sincronização
        await syncRef.set({
            status: 'requested',
            timestamp: new Date().toISOString(),
            logs: ['Sincronização agendada (automática a cada 30 min)']
        }, { merge: true });

        console.log('✅ Sincronização agendada disparada');
        return null;
    });
