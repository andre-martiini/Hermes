import sys

# 1. Fix TaskExecutionView.tsx - close modal automatically on file upload
with open('src/views/TaskExecutionView.tsx', 'r', encoding='utf-8') as f:
    tev_content = f.read()

old_tev = '''      case 'file_upload':
        if (pendingFiles.length > 0) {
          await handleFileUpload(
            pendingFiles.map(file => ({
              file,
              customName: pendingFileNames[getPendingFileKey(file)]
            }))
          );
        }
        break;
    }
    setModalConfig({ ...modalConfig, isOpen: false });
    setModalInputValue('');
    setModalInputName('');
    setPendingFiles([]);
    setPendingFileNames({});
  };'''

new_tev = '''      case 'file_upload':
        if (pendingFiles.length > 0) {
          const filesToUpload = pendingFiles.map(file => ({
            file,
            customName: pendingFileNames[getPendingFileKey(file)]
          }));
          
          setModalConfig({ ...modalConfig, isOpen: false });
          setPendingFiles([]);
          setPendingFileNames({});
          
          handleFileUpload(filesToUpload); // Não usa await aqui para não prender o modal
          return;
        }
        break;
    }
    setModalConfig({ ...modalConfig, isOpen: false });
    setModalInputValue('');
    setModalInputName('');
    setPendingFiles([]);
    setPendingFileNames({});
  };'''

if "handleFileUpload(filesToUpload); // Não usa await" not in tev_content:
    tev_content = tev_content.replace(old_tev, new_tev)

with open('src/views/TaskExecutionView.tsx', 'w', encoding='utf-8', newline='') as f:
    f.write(tev_content)

# 2. Fix DiarioBordoUI.tsx - Add Image Preview
with open('src/views/DiarioBordoUI.tsx', 'r', encoding='utf-8') as f:
    diario_content = f.read()

old_diary = '''    if (richEntry?.type === 'FILE') {
      const nome = richEntry.name || 'Arquivo';
      const url = richEntry.value || '#';
      return (
        <a href={url} target="_blank" rel="noreferrer" className={`group flex items-center gap-2 p-2 rounded-xl border transition-all ${isTimerRunning ? 'bg-white/5 border-white/10 hover:bg-white/10' : 'bg-amber-50/50 border-amber-100 hover:bg-amber-50'}`}>
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${isTimerRunning ? 'bg-white/10 text-white' : 'bg-amber-200 text-amber-600'}`}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className={`text-[11px] font-bold break-all leading-snug ${isTimerRunning ? 'text-white' : 'text-amber-900'}`}>{nome}</p>
            <p className={`text-[8px] uppercase font-black tracking-widest mt-0.5 opacity-50 ${isTimerRunning ? 'text-white/40' : 'text-amber-600'}`}>Anexo</p>
          </div>
        </a>
      );
    }'''

new_diary = '''    if (richEntry?.type === 'FILE') {
      const nome = richEntry.name || 'Arquivo';
      const url = richEntry.value || '#';
      const ext = nome.split('.').pop()?.toLowerCase() || '';
      const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'].includes(ext);

      return (
        <a href={url} target="_blank" rel="noreferrer" className={`group flex flex-col p-2 rounded-xl border transition-all ${isTimerRunning ? 'bg-white/5 border-white/10 hover:bg-white/10' : 'bg-amber-50/50 border-amber-100 hover:bg-amber-50'} overflow-hidden max-w-sm`}>
          {isImage && (
             <div className="w-full h-32 md:h-48 mb-2 bg-slate-900 rounded-lg overflow-hidden flex items-center justify-center">
                <img src={url} alt={nome} className="w-full h-full object-cover opacity-90 group-hover:opacity-100 transition-opacity" />
             </div>
          )}
          <div className="flex items-center gap-2">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${isTimerRunning ? 'bg-white/10 text-white' : 'bg-amber-200 text-amber-600'}`}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-[11px] font-bold break-all leading-snug ${isTimerRunning ? 'text-white' : 'text-amber-900'}`}>{nome}</p>
              <p className={`text-[8px] uppercase font-black tracking-widest mt-0.5 opacity-50 ${isTimerRunning ? 'text-white/40' : 'text-amber-600'}`}>Anexo{isImage ? ' Visual' : ''}</p>
            </div>
          </div>
        </a>
      );
    }'''

if "const isImage = ['jpg', 'jpeg'" not in diario_content:
    diario_content = diario_content.replace(old_diary, new_diary)

with open('src/views/DiarioBordoUI.tsx', 'w', encoding='utf-8', newline='') as f:
    f.write(diario_content)

print("Bugs fixed")
