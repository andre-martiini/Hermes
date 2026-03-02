import re

with open('index.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. QuickLogModal Auto-Submit
old_log = '''          const data = response.data as { raw: string, refined: string };
          if (data.refined) {
            const newText = textInput ? textInput + '\\n' + data.refined : data.refined;
            setTextInput(newText);
          }
        } catch (error) {'''

new_log = '''          const data = response.data as { raw: string, refined: string };
          if (data.refined) {
            const newText = textInput ? textInput + '\\n' + data.refined : data.refined;
            setTextInput(newText);
            if (selectedSystem) {
              onAddLog(newText, selectedSystem);
              setTextInput('');
              onClose();
            }
          }
        } catch (error) {'''

content = content.replace(old_log, new_log)

# 2. TranscriptionAIModal Mobile Upload
old_trans = '''                  </div>
                  <div className="space-y-1">
                    <p className="font-black text-slate-900">Cole seu áudio aqui (Ctrl+V)</p>
                    <p className="text-slate-400 text-xs font-medium">Ou arraste o arquivo aqui</p>
                  </div>
                </div>'''

new_trans = '''                  </div>
                  <div className="space-y-1">
                    <p className="font-black text-slate-900">Cole seu áudio aqui (Ctrl+V)</p>
                    <p className="text-slate-400 text-xs font-medium">Ou arraste o arquivo aqui</p>
                  </div>
                  <div className="mt-6 md:hidden">
                    <button
                      onClick={() => document.getElementById('mobile-transcription-upload')?.click()}
                      className="bg-indigo-100 text-indigo-700 px-6 py-3 rounded-xl font-black uppercase tracking-widest text-[10px] shadow-sm hover:bg-indigo-200 transition-all flex items-center gap-2 mx-auto"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                      Selecionar Arquivo
                    </button>
                    <input
                      id="mobile-transcription-upload"
                      type="file"
                      className="hidden"
                      accept="audio/*,video/*"
                      onChange={(e: any) => {
                        if (e.target.files && e.target.files.length > 0) {
                          handleFileSelection(e.target.files[0]);
                        }
                      }}
                    />
                  </div>
                </div>'''

content = content.replace(old_trans, new_trans)

# 3. Toast Action for Task Creation
old_task = '''      if (convertingIdea) {
        await deleteDoc(doc(db, 'brainstorm_ideas', convertingIdea.id));
        setConvertingIdea(null);
        setTaskInitialData(null);
      }
      showToast("Nova ação criada!", 'success');
    } catch (err) {
      console.error("Erro ao criar tarefa:", err);'''

new_task = '''      if (convertingIdea) {
        await deleteDoc(doc(db, 'brainstorm_ideas', convertingIdea.id));
        setConvertingIdea(null);
        setTaskInitialData(null);
      }

      showToast("Nova ação criada!", 'success', {
        label: "Ver Ação",
        onClick: () => {
          setSelectedTask({
            id: docRef.id,
            ...data,
            google_id: "",
            data_atualizacao: new Date().toISOString(),
            projeto: 'Google Tasks',
            prioridade: 'média',
            contabilizar_meta: data.categoria === 'CLC' || data.categoria === 'ASSISTÊNCIA',
            acompanhamento: [],
            entregas_relacionadas: []
          } as Tarefa);
          setTaskModalMode('default');
        }
      });
    } catch (err) {
      console.error("Erro ao criar tarefa:", err);'''

# also fix docRef inside handleCreateTarefa
old_adddoc = '''await addDoc(collection(db, 'tarefas'), {'''
new_adddoc = '''const docRef = await addDoc(collection(db, 'tarefas'), {'''

content = content.replace(old_task, new_task)
content = content.replace(old_adddoc, new_adddoc, 1)

with open('index.tsx', 'w', encoding='utf-8', newline='') as f:
    f.write(content)

print("Updates index.tsx OK")
