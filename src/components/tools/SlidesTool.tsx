import React, { useState } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../../firebase';
import { AutoExpandingTextarea } from '../ui/UIComponents';

const SlidesTool = ({ onBack, showToast }: { onBack: () => void, showToast: (msg: string, type: 'success' | 'error' | 'info') => void }) => {
  const [rascunho, setRascunho] = useState('');
  const [qtdSlides, setQtdSlides] = useState(5);
  const [isGenerating, setIsGenerating] = useState(false);
  const [presentation, setPresentation] = useState<any>(null);
  const [currentHistoryId, setCurrentHistoryId] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ slideIdx: number; topicoIdx: number } | null>(null);
  const [editValue, setEditValue] = useState('');
  const [view, setView] = useState<'editor' | 'history'>('editor');
  const [history, setHistory] = useState<SlideHistoryEntry[]>(() => {
    try { return JSON.parse(localStorage.getItem(SLIDES_HISTORY_KEY) || '[]'); } catch { return []; }
  });

  const saveToHistory = (data: any, draft: string, existingId?: string | null) => {
    const title = data?.slides?.[0]?.titulo || 'Apresentação';
    const entry: SlideHistoryEntry = { id: existingId || `slides_${Date.now()}`, title, createdAt: new Date().toISOString(), slides: data.slides, rascunho: draft };
    setHistory(prev => { const updated = [entry, ...prev.filter(e => e.id !== entry.id)].slice(0, 30); localStorage.setItem(SLIDES_HISTORY_KEY, JSON.stringify(updated)); return updated; });
    return entry.id;
  };

  const syncHistory = (updatedPresentation: any) => {
    if (!currentHistoryId) return;
    setHistory(prev => { const updated = prev.map(e => e.id === currentHistoryId ? { ...e, slides: updatedPresentation.slides, title: updatedPresentation.slides?.[0]?.titulo || e.title } : e); localStorage.setItem(SLIDES_HISTORY_KEY, JSON.stringify(updated)); return updated; });
  };

  const handleGenerate = async () => {
    if (!rascunho.trim()) { showToast("Insira o texto bruto para começar.", "info"); return; }
    setIsGenerating(true); setPresentation(null); setEditing(null); setCurrentHistoryId(null);
    try {
      let data: any;
      if (import.meta.env.DEV) {
        const response = await fetch('/proxy-functions/gerarSlidesIA', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ data: { rascunho, qtdSlides } }) });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const result = await response.json();
        data = result.result || result.data;
      } else {
        const gerarSlidesFn = httpsCallable(functions, 'gerarSlidesIA');
        data = (await gerarSlidesFn({ rascunho, qtdSlides })).data;
      }
      setPresentation(data);
      setCurrentHistoryId(saveToHistory(data, rascunho));
      showToast("Apresentação gerada com sucesso!", "success");
    } catch (err) { console.error(err); showToast("Erro ao gerar slides.", "error"); }
    finally { setIsGenerating(false); }
  };

  const handleExportPPTX = async () => {
    if (!presentation?.slides) return;
    try {
      const pptxgen = (await import('pptxgenjs')).default;
      const pres = new pptxgen();
      presentation.slides.forEach((si: any) => {
        const slide = pres.addSlide();
        if (si.layout === 'capa') {
          slide.background = { color: '1e293b' };
          slide.addText(si.titulo, { x: 1, y: 2, w: '80%', h: 1, fontSize: 44, color: 'FFFFFF', bold: true, align: 'center' });
          if (si.topicos?.length > 0) slide.addText(si.topicos[0], { x: 1, y: 3.5, w: '80%', fontSize: 24, color: 'cbd5e1', align: 'center' });
        } else {
          slide.background = { color: 'FFFFFF' };
          slide.addText(si.titulo, { x: 0.5, y: 0.5, w: '90%', h: 0.8, fontSize: 32, color: '1e293b', bold: true });
          slide.addShape(pres.ShapeType.line, { x: 0.5, y: 1.3, w: '90%', h: 0, line: { color: 'f97316', width: 2 } });
          if (Array.isArray(si.topicos)) si.topicos.forEach((t: string, i: number) => slide.addText(t, { x: 0.8, y: 1.8 + i * 0.8, w: '85%', h: 0.6, fontSize: 18, color: '475569', bullet: true }));
        }
        slide.addText('Gerado por Hermes AI', { x: 0.5, y: 5.2, fontSize: 10, color: '94a3b8' });
      });
      await pres.writeFile({ fileName: `${presentation.slides?.[0]?.titulo || 'apresentacao'}.pptx` });
      showToast("PPTX exportado com sucesso!", "success");
    } catch (e) { console.error(e); showToast("Erro ao gerar PPTX.", "error"); }
  };

  const startEditing = (slideIdx: number, topicoIdx: number, val: string) => { setEditing({ slideIdx, topicoIdx }); setEditValue(val); };

  const commitEdit = () => {
    if (!editing || !presentation) return;
    const updated = { ...presentation, slides: presentation.slides.map((s: any, si: number) => {
      if (si !== editing.slideIdx) return s;
      if (editing.topicoIdx === -1) return { ...s, titulo: editValue };
      const nt = [...s.topicos]; nt[editing.topicoIdx] = editValue; return { ...s, topicos: nt };
    })};
    setPresentation(updated); syncHistory(updated); setEditing(null);
  };

  const addTopico = (si: number) => {
    const novo = 'Novo tópico';
    const updated = { ...presentation, slides: presentation.slides.map((s: any, i: number) => i !== si ? s : { ...s, topicos: [...(s.topicos || []), novo] }) };
    setPresentation(updated); syncHistory(updated);
    startEditing(si, updated.slides[si].topicos.length - 1, novo);
  };

  const removeTopico = (si: number, ti: number) => {
    const updated = { ...presentation, slides: presentation.slides.map((s: any, i: number) => i !== si ? s : { ...s, topicos: s.topicos.filter((_: any, j: number) => j !== ti) }) };
    setPresentation(updated); syncHistory(updated);
  };

  const loadFromHistory = (entry: SlideHistoryEntry) => { setPresentation({ slides: entry.slides }); setRascunho(entry.rascunho); setCurrentHistoryId(entry.id); setEditing(null); setView('editor'); };

  const deleteFromHistory = (id: string) => {
    setHistory(prev => { const u = prev.filter(e => e.id !== id); localStorage.setItem(SLIDES_HISTORY_KEY, JSON.stringify(u)); return u; });
    if (currentHistoryId === id) { setPresentation(null); setCurrentHistoryId(null); }
  };

  // --- JSX helpers ---
  const SlideCard = ({ slide, idx }: { slide: any, idx: number }) => (
    <div className="bg-slate-900 rounded-[2.5rem] p-10 min-h-[400px] flex flex-col justify-between shadow-2xl relative overflow-hidden group border border-white/5">
      <div className="absolute -top-10 -right-10 w-40 h-40 bg-white/5 rounded-full blur-3xl group-hover:bg-white/10 transition-all duration-700"></div>
      <div className="absolute -bottom-10 -left-10 w-60 h-60 bg-orange-500/10 rounded-full blur-3xl group-hover:bg-orange-500/20 transition-all duration-700"></div>
      <div className="relative z-10 flex-1">
        <div className="flex justify-between items-start mb-8">
          <span className="text-[10px] font-black text-white/30 uppercase tracking-[0.3em]">Slide {slide.numero} • {slide.layout}</span>
          <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <button onClick={() => addTopico(idx)} title="Adicionar tópico" className="w-7 h-7 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white/60 hover:text-white transition-all">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
            </button>
            <button onClick={() => { navigator.clipboard.writeText(`${slide.titulo}\n${slide.topicos.join('\n')}`); showToast("Copiado!", "success"); }} className="w-7 h-7 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white/60 hover:text-white transition-all">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
            </button>
          </div>
        </div>
        {editing?.slideIdx === idx && editing?.topicoIdx === -1 ? (
          <input autoFocus value={editValue} onChange={e => setEditValue(e.target.value)} onBlur={commitEdit} onKeyDown={e => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') setEditing(null); }}
            className={`w-full bg-white/10 text-white rounded-xl px-3 py-2 outline-none ring-2 ring-orange-500 font-black tracking-tight leading-tight mb-8 ${slide.layout === 'capa' ? 'text-4xl' : 'text-2xl'}`} />
        ) : (
          <h3 onClick={() => startEditing(idx, -1, slide.titulo)} title="Clique para editar o título" className={`font-black text-white tracking-tight leading-tight mb-8 cursor-pointer hover:text-orange-300 transition-colors group/title ${slide.layout === 'capa' ? 'text-5xl' : 'text-3xl'}`}>
            {slide.titulo}
            <svg className="inline w-3.5 h-3.5 ml-2 opacity-0 group-hover/title:opacity-40 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
          </h3>
        )}
        <ul className="space-y-3">
          {Array.isArray(slide.topicos) && slide.topicos.map((t: any, ti: number) => (
            <li key={ti} className="flex gap-3 items-start text-white/80 group/topico">
              <span className="w-2 h-2 bg-orange-500 rounded-full mt-2.5 flex-shrink-0"></span>
              {editing?.slideIdx === idx && editing?.topicoIdx === ti ? (
                <input autoFocus value={editValue} onChange={e => setEditValue(e.target.value)} onBlur={commitEdit} onKeyDown={e => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') setEditing(null); }} className="flex-1 bg-white/10 text-white rounded-lg px-2 py-1 outline-none ring-2 ring-orange-500 text-base font-medium" />
              ) : (
                <span onClick={() => startEditing(idx, ti, typeof t === 'string' ? t : String(t))} title="Clique para editar" className="flex-1 text-lg font-medium leading-relaxed cursor-pointer hover:text-orange-300 transition-colors">
                  {typeof t === 'string' ? t : (typeof t === 'object' ? JSON.stringify(t) : String(t))}
                </span>
              )}
              <button onClick={() => removeTopico(idx, ti)} title="Remover" className="opacity-0 group-hover/topico:opacity-100 w-5 h-5 rounded-full bg-white/10 hover:bg-rose-500/50 flex items-center justify-center text-white/40 hover:text-white transition-all flex-shrink-0 mt-1.5">
                <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </li>
          ))}
        </ul>
      </div>
      {slide.prompt_imagem && (
        <div className="relative z-10 mt-10 pt-8 border-t border-white/10">
          <div className="flex items-center gap-2 text-white/40 mb-3">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
            <span className="text-[10px] font-black uppercase tracking-widest">IA Image Prompt</span>
          </div>
          <p className="text-xs text-white/40 italic leading-relaxed">{slide.prompt_imagem}</p>
        </div>
      )}
    </div>
  );

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 space-y-8 pb-32">
      {/* Header com toggle */}
      <div className="flex items-center gap-6 mb-4">
        <button onClick={onBack} className="w-12 h-12 bg-white rounded-2xl flex items-center justify-center text-slate-400 hover:text-slate-900 border border-slate-200 hover:border-slate-900 transition-all shadow-sm">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
        </button>
        <div className="flex-1">
          <h2 className="text-3xl font-black text-slate-900 tracking-tighter">Gerador de Slides IA</h2>
          <p className="text-slate-500 font-medium">Transforme textos complexos em apresentações profissionais.</p>
        </div>
        <div className="flex bg-slate-100 p-1 rounded-2xl">
          <button onClick={() => setView('editor')} className={`px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${view === 'editor' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}>Editor</button>
          <button onClick={() => setView('history')} className={`px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center gap-2 ${view === 'history' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}>
            Histórico
            {history.length > 0 && <span className="bg-orange-500 text-white text-[8px] font-black px-1.5 py-0.5 rounded-full">{history.length}</span>}
          </button>
        </div>
      </div>

      {/* ===== HISTÓRICO ===== */}
      {view === 'history' && (
        <div className="animate-in fade-in duration-300">
          {history.length === 0 ? (
            <div className="py-24 flex flex-col items-center justify-center text-slate-300 space-y-4">
              <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              <p className="font-black uppercase tracking-widest text-sm">Nenhuma apresentação salva ainda</p>
            </div>
          ) : (
            <div className="space-y-3">
              {history.map(entry => (
                <div key={entry.id} className={`bg-white rounded-[2rem] border p-6 flex items-center gap-6 shadow-sm hover:shadow-md transition-all group ${currentHistoryId === entry.id ? 'border-orange-300 ring-2 ring-orange-100' : 'border-slate-100'}`}>
                  <div className="w-16 h-12 bg-slate-900 rounded-xl flex-shrink-0 flex items-center justify-center">
                    <span className="text-[8px] font-black text-white/60 uppercase">{entry.slides.length}s</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-black text-slate-900 truncate leading-tight">{entry.title}</p>
                    <p className="text-[10px] font-bold text-slate-400 mt-0.5">
                      {entry.slides.length} slides &nbsp;•&nbsp;
                      {new Date(entry.createdAt).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </p>
                    {entry.rascunho && <p className="text-[10px] text-slate-300 font-medium mt-1 truncate">{entry.rascunho.slice(0, 80)}...</p>}
                  </div>
                  <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                    {currentHistoryId === entry.id && <span className="text-[8px] font-black text-orange-500 uppercase tracking-widest">Ativa</span>}
                    <button onClick={() => loadFromHistory(entry)} title="Carregar e editar" className="flex items-center gap-1.5 px-4 py-2 bg-slate-900 text-white rounded-xl text-[9px] font-black uppercase tracking-widest hover:bg-slate-700 transition-all">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                      Editar
                    </button>
                    <button onClick={() => deleteFromHistory(entry.id)} title="Excluir do histórico" className="p-2 rounded-xl text-slate-300 hover:text-rose-500 hover:bg-rose-50 transition-all">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                    </button>
                  </div>
                </div>
              ))}
              {history.length >= 5 && (
                <button onClick={() => { if (window.confirm(`Excluir todo o histórico (${history.length} apresentações)?`)) { setHistory([]); localStorage.removeItem(SLIDES_HISTORY_KEY); if (currentHistoryId) { setPresentation(null); setCurrentHistoryId(null); } } }}
                  className="w-full mt-4 py-3 text-[9px] font-black uppercase tracking-widest text-slate-300 hover:text-rose-500 transition-colors"
                >Limpar todo o histórico
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* ===== EDITOR ===== */}
      {view === 'editor' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div className="space-y-6">
            <div className="bg-white p-8 rounded-[2.5rem] border border-slate-200 shadow-xl space-y-6">
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3 ml-1">Conteúdo Base (Texto Bruto)</label>
                <AutoExpandingTextarea className="w-full bg-slate-50 border border-slate-100 rounded-[1.5rem] p-6 text-slate-800 font-bold leading-relaxed outline-none focus:ring-4 focus:ring-orange-100 transition-all min-h-[300px]"
                  placeholder="Cole aqui o texto, atas de reunião, artigos ou tópicos que deseja transformar em slides..."
                  value={rascunho} onChange={e => setRascunho(e.target.value)} />
              </div>
              <div className="flex items-end gap-6">
                <div className="flex-1">
                  <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3 ml-1">Quantidade de Slides</label>
                  <input type="number" min="1" max="20" className="w-full bg-slate-50 border border-slate-100 rounded-2xl p-4 text-slate-800 font-black outline-none focus:ring-4 focus:ring-orange-100 transition-all" value={qtdSlides} onChange={e => setQtdSlides(parseInt(e.target.value))} />
                </div>
                <button onClick={handleGenerate} disabled={isGenerating} className={`flex-[2] h-14 bg-slate-900 text-white rounded-2xl font-black uppercase tracking-widest text-xs flex items-center justify-center gap-3 shadow-xl transition-all hover:scale-[1.02] active:scale-95 disabled:opacity-50 disabled:grayscale ${isGenerating ? 'animate-pulse' : ''}`}>
                  {isGenerating ? (<><div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>Processando...</>) : (<><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>Gerar Apresentação</>)}
                </button>
              </div>
            </div>

            {presentation && (
              <div className="bg-white p-5 rounded-[2rem] border border-slate-200 shadow-lg flex items-center justify-between gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div>
                  <p className="text-xs font-black text-slate-900">{presentation.slides?.length} slides gerados</p>
                  <p className="text-[10px] text-slate-400 font-medium">Clique em qualquer título ou tópico para editar</p>
                </div>
                <div className="flex gap-3">
                  <button onClick={() => { const t = presentation.slides.map((s: any) => `${s.titulo}\n${(s.topicos || []).join('\n')}`).join('\n\n'); navigator.clipboard.writeText(t); showToast("Conteúdo copiado!", "success"); }}
                    className="flex items-center gap-2 px-4 py-2.5 bg-slate-100 text-slate-600 rounded-xl text-[9px] font-black uppercase tracking-widest hover:bg-slate-200 transition-all">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                    Copiar Tudo
                  </button>
                  <button onClick={handleExportPPTX} className="flex items-center gap-2 px-4 py-2.5 bg-orange-500 text-white rounded-xl text-[9px] font-black uppercase tracking-widest hover:bg-orange-600 transition-all shadow-lg shadow-orange-200">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                    Exportar PPTX
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="space-y-8 h-[700px] overflow-y-auto pr-4 custom-scrollbar">
            {presentation ? (
              presentation.slides.map((slide: any, idx: number) => <SlideCard key={idx} slide={slide} idx={idx} />)
            ) : isGenerating ? (
              <div className="h-full flex flex-col items-center justify-center space-y-4 animate-pulse">
                <div className="w-16 h-16 bg-slate-100 rounded-full"></div>
                <p className="text-slate-300 font-black uppercase tracking-widest">Arquitetando Slides...</p>
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center space-y-6 text-slate-200">
                <svg className="w-24 h-24" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
                <div className="text-center space-y-3">
                  <p className="font-bold">Nenhuma apresentação gerada.<br/><span className="text-sm font-medium opacity-60">Seus slides aparecerão aqui.</span></p>
                  {history.length > 0 && <button onClick={() => setView('history')} className="text-[10px] font-black uppercase tracking-widest text-orange-400 hover:text-orange-500 transition-colors">Ver {history.length} apresentação{history.length > 1 ? 'ões' : ''} salva{history.length > 1 ? 's' : ''} →</button>}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};



const SHOPPING_LOCATIONS_KEY = 'hermes_shopping_locations';
const SHOPPING_ITEMS_KEY = 'hermes_shopping_items';

export { SlidesTool };
