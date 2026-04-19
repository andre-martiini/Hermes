const fs = require('fs');
const content = fs.readFileSync('src/components/tools/SlidesTool.tsx', 'utf8');

let newContent = content.replace(
  "import { doc, getDoc } from 'firebase/firestore';",
  "import { doc, getDoc, collection, query, where, onSnapshot, orderBy } from 'firebase/firestore';"
);

newContent = newContent.replace(
  "import { AutoExpandingTextarea } from '../ui/UIComponents';",
  "import { AutoExpandingTextarea } from '../ui/UIComponents';\nimport { useAuth } from '@/hooks/useAuth';"
);

newContent = newContent.replace(
  "export const SlidesTool: React.FC<SlidesToolProps> = ({ onBack, showToast, initialDraftId }) => {",
  "export const SlidesTool: React.FC<SlidesToolProps> = ({ onBack, showToast, initialDraftId }) => {\n  const { user } = useAuth();"
);

newContent = newContent.replace(
  "const [isGenerating, setIsGenerating] = useState(false);",
  "const [isGenerating, setIsGenerating] = useState(false);\n  const [isSubmittingJob, setIsSubmittingJob] = useState(false);"
);

newContent = newContent.replace(
  "try { return JSON.parse(localStorage.getItem(SLIDES_HISTORY_KEY) || '[]'); } catch { return []; }\n  });",
  "try { return JSON.parse(localStorage.getItem(SLIDES_HISTORY_KEY) || '[]'); } catch { return []; }\n  });\n  const [jobs, setJobs] = useState<any[]>([]);\n\n  // Escutar jobs do Firestore em tempo real\n  useEffect(() => {\n    if (!user) return;\n    const q = query(\n      collection(db, 'slide_jobs'),\n      where('userId', '==', user.uid),\n      orderBy('timestamp', 'desc')\n    );\n    const unsubscribe = onSnapshot(q, (snapshot) => {\n      const newJobs = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));\n      setJobs(newJobs);\n    });\n    return () => unsubscribe();\n  }, [user]);"
);

newContent = newContent.replace(
  /const handleExportPPTX = async \(\) => \{[\s\S]*?catch \(e\) \{ console\.error\(e\); showToast\("Erro ao gerar PPTX\.", "error"\); \}\n  \};/,
  `const handleDispatchJob = async () => {
    if (!presentation?.slides || !user) return;
    setIsSubmittingJob(true);
    try {
      const iniciarJobSlides = httpsCallable(functions, 'iniciarJobSlides');
      await iniciarJobSlides({
        rascunho: rascunho,
        slides: presentation.slides
      });
      showToast("Job de exportação iniciado no backend!", "success");
      setView('history');
    } catch (e) {
      console.error(e);
      showToast("Erro ao iniciar job de exportação.", "error");
    } finally {
      setIsSubmittingJob(false);
    }
  };`
);

const jobsJSX = `
          {jobs.length > 0 && (
            <div className="mb-8 space-y-3">
              <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-400 ml-1">Jobs de Processamento em Nuvem</h3>
              {jobs.map(job => (
                <div key={job.id} className="bg-white rounded-[2rem] border border-orange-100 p-6 flex flex-col gap-4 shadow-sm relative overflow-hidden">
                  {job.status === 'processing' && <div className="absolute top-0 left-0 w-full h-1 bg-orange-100"><div className="h-full bg-orange-500 animate-pulse w-1/2 rounded-r-full"></div></div>}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className={\`w-12 h-12 rounded-xl flex items-center justify-center \${job.status === 'completed' ? 'bg-emerald-100 text-emerald-600' : job.status === 'error' ? 'bg-rose-100 text-rose-600' : 'bg-orange-100 text-orange-600 animate-pulse'}\`}>
                        {job.status === 'completed' ? (
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                        ) : job.status === 'error' ? (
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                        ) : (
                          <svg className="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                        )}
                      </div>
                      <div>
                        <p className="text-sm font-black text-slate-900">{job.tema ? job.tema.slice(0, 40) + '...' : 'Apresentação'}</p>
                        <p className="text-[10px] font-bold text-slate-400 mt-0.5">
                          {job.status === 'processing' ? 'Processando...' : job.status === 'completed' ? 'Concluído' : 'Erro'} • {job.totalSlides} slides
                        </p>
                      </div>
                    </div>
                    {job.driveLink && (
                      <a href={job.driveLink} target="_blank" rel="noopener noreferrer" className="px-4 py-2 bg-emerald-50 text-emerald-600 rounded-xl text-[9px] font-black uppercase tracking-widest hover:bg-emerald-100 transition-colors flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                        Abrir no Drive
                      </a>
                    )}
                  </div>
                  {job.status === 'processing' && (
                    <div className="flex gap-1 mt-2">
                      {job.slides_status?.map((s: any, i: number) => (
                        <div key={i} className={\`h-1.5 flex-1 rounded-full \${s.status === 'completed' ? 'bg-emerald-500' : s.status === 'error' ? 'bg-rose-500' : s.status === 'processing' ? 'bg-orange-500 animate-pulse' : 'bg-slate-200'}\`} title={\`Slide \${i + 1}: \${s.status}\`}></div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-400 ml-1 mb-3">Histórico de Rascunhos</h3>
`;

newContent = newContent.replace(
  '<div className="animate-in fade-in duration-300">',
  '<div className="animate-in fade-in duration-300">\n' + jobsJSX
);

newContent = newContent.replace(
  '<button onClick={handleExportPPTX} className="flex items-center gap-2 px-4 py-2.5 bg-orange-500 text-white rounded-xl text-[9px] font-black uppercase tracking-widest hover:bg-orange-600 transition-all shadow-lg shadow-orange-200">\n                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>\n                    Exportar PPTX\n                  </button>',
  `<button onClick={handleDispatchJob} disabled={isSubmittingJob || jobs.some(j => j.status === 'processing')} className={\`flex items-center gap-2 px-4 py-2.5 bg-orange-500 text-white rounded-xl text-[9px] font-black uppercase tracking-widest hover:bg-orange-600 transition-all shadow-lg shadow-orange-200 disabled:opacity-50 disabled:grayscale \${isSubmittingJob ? 'animate-pulse' : ''}\`}>
                    {isSubmittingJob ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div> : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>}
                    Aprovar e Exportar Assíncrono PPTX
                  </button>`
);

fs.writeFileSync('src/components/tools/SlidesTool.tsx', newContent);
