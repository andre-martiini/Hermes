
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Tarefa, Status, EntregaInstitucional, Prioridade, AtividadeRealizada,
  Afastamento, PlanoTrabalho, PlanoTrabalhoItem, Categoria, Acompanhamento,
  BrainstormIdea, FinanceTransaction, FinanceGoal, FinanceSettings,
  FixedBill, BillRubric, IncomeEntry, IncomeRubric, HealthWeight,
  DailyHabits, HealthSettings, HermesNotification, AppSettings,
  formatDate, formatDateLocalISO, Sistema, SistemaStatus, WorkItem, WorkItemPhase,
  WorkItemPriority, QualityLog, WorkItemAudit, GoogleCalendarEvent,
  PoolItem, CustomNotification, HealthExam, ConhecimentoItem, UndoAction, HermesModalProps,
  ShoppingItem
} from './types';
import HealthView from './HealthView';
import { STATUS_COLORS, PROJECT_COLORS } from './constants';
import { db, functions, messaging, auth, googleProvider, signInWithPopup, signOut, browserLocalPersistence, browserSessionPersistence, setPersistence } from './firebase';
import { onAuthStateChanged, User } from 'firebase/auth';
import { collection, onSnapshot, query, orderBy, updateDoc, doc, addDoc, deleteDoc, setDoc, arrayUnion, arrayRemove, writeBatch, getDoc } from 'firebase/firestore';
import { getToken, onMessage } from 'firebase/messaging';
import { httpsCallable } from 'firebase/functions';
import { GoogleGenerativeAI } from "@google/generative-ai";
import FinanceView from './FinanceView';
import DashboardView from './DashboardView';
import KnowledgeView from './KnowledgeView';
import ProjectsView from './ProjectsView';

// Importações dos módulos extraídos pelo split.js
import {
  DEFAULT_APP_SETTINGS, getDaysInMonth, isWorkDay, callScrapeSipac,
  getMonthWorkDays, normalizeStatus, formatWhatsAppText,
  formatInlineWhatsAppText, detectAreaFromTitle
} from './src/utils/helpers';
import {
  ToastContainer, FilterChip, PgcMiniTaskCard, PgcAuditRow,
  RowCard, WysiwygEditor, NotificationCenter, AutoExpandingTextarea
} from './src/components/ui/UIComponents';
import {
  HermesModal, SettingsModal, DailyHabitsModal,
  TaskCreateModal, TaskEditModal
} from './src/components/modals/Modals';
import { DayView } from './src/views/DayView';
import { CalendarView } from './src/views/CalendarView';
import { CategoryView } from './src/views/CategoryView';
import { TaskExecutionView } from './src/views/TaskExecutionView';
import { PublicScholarshipRegistration } from './src/components/public/PublicScholarshipRegistration';
import { TranscriptionTool } from './src/components/tools/TranscriptionTool';
import { ShoppingListTool } from './src/components/tools/ShoppingListTool';
import { SpeedDialMenu } from './src/components/ui/SpeedDialMenu';
import { generateMarkdown, downloadMarkdown } from './src/utils/markdownGenerator';


type SortOption = 'date-asc' | 'date-desc' | 'priority-high' | 'priority-low';
type DateFilter = 'today' | 'week' | 'month';

interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error' | 'info';
  action?: { label: string | React.ReactNode, onClick: () => void };
  actions?: { label: string | React.ReactNode, onClick: () => void }[];
}

// --- Utilitários ---
// Moved formatDate to types.ts to break circular dependency


// --- Subcomponentes Atômicos ---
// --- Components ---
// Função para detectar automaticamente a área baseada em palavras-chave
// WorkItem modals removed in favor of inline logs
const SLIDES_HISTORY_KEY = 'hermes_slides_history';
interface SlideHistoryEntry { id: string; title: string; createdAt: string; slides: any[]; rascunho: string; }

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
    const updated = {
      ...presentation, slides: presentation.slides.map((s: any, si: number) => {
        if (si !== editing.slideIdx) return s;
        if (editing.topicoIdx === -1) return { ...s, titulo: editValue };
        const nt = [...s.topicos]; nt[editing.topicoIdx] = editValue; return { ...s, topicos: nt };
      })
    };
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
                  <p className="font-bold">Nenhuma apresentação gerada.<br /><span className="text-sm font-medium opacity-60">Seus slides aparecerão aqui.</span></p>
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






const FerramentasView = ({
  ideas,
  onDeleteIdea,
  onArchiveIdea,
  onAddTextIdea,
  onUpdateIdea,
  onConvertToLog,
  onConvertToTask,
  activeTool,
  setActiveTool,
  isAddingText,
  setIsAddingText,
  showToast,
  showAlert
}: {
  ideas: BrainstormIdea[],
  onDeleteIdea: (id: string) => void,
  onArchiveIdea: (id: string) => void,
  onAddTextIdea: (text: string) => void,
  onUpdateIdea: (id: string, text: string) => void,
  onConvertToLog: (idea: BrainstormIdea) => void,
  onConvertToTask: (idea: BrainstormIdea) => void,
  activeTool: 'brainstorming' | 'slides' | 'shopping' | 'transcription' | null,
  setActiveTool: (tool: 'brainstorming' | 'slides' | 'shopping' | 'transcription' | null) => void,
  isAddingText: boolean,
  setIsAddingText: (val: boolean) => void,
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void,
  showAlert: (title: string, msg: string) => void
}) => {
  const [isProcessing, setIsProcessing] = useState(false);
  const [textInput, setTextInput] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [sortOrder, setSortOrder] = useState<'date-desc' | 'date-asc'>('date-desc');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isArchivedIdeasOpen, setIsArchivedIdeasOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  // Gravador
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const activeIdeas = ideas
    .filter(i => i.status !== 'archived')
    .filter(i => i.text.toLowerCase().includes(searchTerm.toLowerCase()))
    .sort((a, b) => {
      if (sortOrder === 'date-desc') return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    });

  const archivedIdeas = ideas
    .filter(i => i.status === 'archived')
    .filter(i => i.text.toLowerCase().includes(searchTerm.toLowerCase()))
    .sort((a, b) => {
      if (sortOrder === 'date-desc') return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    });

  const toggleCardExpansion = (id: string) => {
    setExpandedCards(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  if (activeTool === 'slides') {
    return <SlidesTool onBack={() => setActiveTool(null)} showToast={showToast} />;
  }

  if (activeTool === 'shopping') {
    return <ShoppingListTool onBack={() => setActiveTool(null)} showToast={showToast} />;
  }

  if (activeTool === 'transcription') {
    return <TranscriptionTool onBack={() => setActiveTool(null)} showToast={showToast} />;
  }

  if (!activeTool) {
    return (
      <div className="animate-in grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-0 md:gap-8 pb-20 px-0">
        <button
          onClick={() => setActiveTool('brainstorming')}
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-200 shadow-none md:shadow-xl hover:shadow-none md:hover:shadow-2xl transition-all group text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 -ml-px -mt-px md:m-0"
        >
          <div className="w-12 h-12 md:w-16 md:h-16 bg-blue-50 rounded-none md:rounded-2xl flex items-center justify-center text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-all flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-900 tracking-tighter mb-1 md:mb-2">Notas Rápidas</h3>
            <p className="text-slate-500 font-medium leading-relaxed text-xs md:text-base">Registre notas rápidas para organizar depois.</p>
          </div>
        </button>

        <button
          onClick={() => setActiveTool('slides')}
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-200 shadow-none md:shadow-xl hover:shadow-none md:hover:shadow-2xl transition-all group text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 -ml-px -mt-px md:m-0"
        >
          <div className="w-12 h-12 md:w-16 md:h-16 bg-orange-50 rounded-none md:rounded-2xl flex items-center justify-center text-orange-600 group-hover:bg-orange-600 group-hover:text-white transition-all flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-900 tracking-tighter mb-1 md:mb-2">Gerador de Slides</h3>
            <p className="text-slate-500 font-medium leading-relaxed text-xs md:text-base">Crie apresentações profissionais com IA de forma rápida.</p>
          </div>
        </button>
        <button
          onClick={() => setActiveTool('shopping')}
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-200 shadow-none md:shadow-xl hover:shadow-none md:hover:shadow-2xl transition-all group text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 -ml-px -mt-px md:m-0"
        >
          <div className="w-12 h-12 md:w-16 md:h-16 bg-emerald-50 rounded-none md:rounded-2xl flex items-center justify-center text-emerald-600 group-hover:bg-emerald-600 group-hover:text-white transition-all flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-900 tracking-tighter mb-1 md:mb-2">Lista de Compras</h3>
            <p className="text-slate-500 font-medium leading-relaxed text-xs md:text-base">Organize suas compras por estabelecimento e categorias.</p>
          </div>
        </button>

        <button
          onClick={() => setActiveTool('transcription')}
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-200 shadow-none md:shadow-xl hover:shadow-none md:hover:shadow-2xl transition-all group text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 -ml-px -mt-px md:m-0"
        >
          <div className="w-12 h-12 md:w-16 md:h-16 bg-purple-50 rounded-none md:rounded-2xl flex items-center justify-center text-purple-600 group-hover:bg-purple-600 group-hover:text-white transition-all flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-900 tracking-tighter mb-1 md:mb-2">Transcrição de Áudio</h3>
            <p className="text-slate-500 font-medium leading-relaxed text-xs md:text-base">Transcreva e refine áudios do WhatsApp e outros.</p>
          </div>
        </button>

      </div>
    );
  }

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/m4a' }); // ou audio/webm
        await handleProcessAudio(audioBlob);

        // Parar todas as tracks para desligar o ícone de microfone do navegador
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Erro ao acessar microfone:", err);
      showAlert("Erro", "Permissão de microfone negada ou não disponível.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleProcessAudio = async (audioBlob: Blob) => {
    setIsProcessing(true);
    try {
      // Converter Blob para Base64
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];

          // Chamar a Cloud Function
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String });
          const data = response.data as { raw: string, refined: string };

          // Adicionar a ideia transcrita ao banco
          if (data.refined) {
            onAddTextIdea(data.refined);
          }
        } catch (error) {
          console.error("Erro ao transcrever:", error);
          showAlert("Erro", "Erro ao processar áudio via Hermes AI.");
        } finally {
          setIsProcessing(false);
        }
      };
    } catch (error) {
      console.error("Erro ao ler áudio:", error);
      setIsProcessing(false);
    }
  };

  return (
    <>
      <div className="animate-in space-y-12 pb-40">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setActiveTool(null)}
              className="p-3 bg-white border border-slate-200 rounded-none md:rounded-2xl text-slate-400 hover:text-slate-900 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
            </button>
            <h3 className="text-2xl font-black text-slate-900 tracking-tight uppercase tracking-widest text-[10px]">Ferramentas / Notas Rápidas</h3>
          </div>
        </div>

        <div className="space-y-4 max-w-4xl mx-auto w-full">
          <div className="flex flex-col md:flex-row gap-4 w-full px-0">
            <div className="flex-1 bg-white border border-slate-200 rounded-none md:rounded-xl px-4 py-3 flex items-center gap-3 shadow-none md:shadow-sm focus-within:ring-2 focus-within:ring-blue-100 transition-all">
              <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
              <input
                type="text"
                placeholder="Pesquisar nas notas..."
                className="flex-1 bg-transparent outline-none text-xs md:text-sm font-bold text-slate-700 placeholder:text-slate-400"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
              />
            </div>
          </div>

          {/* Inserção de Nova Ideia via Digitação */}
          <div className="w-full animate-in slide-in-from-top-2 duration-500">
            <div className="bg-white p-2 rounded-none md:rounded-[2rem] border-2 border-slate-100 shadow-none md:shadow-xl flex items-center gap-4 focus-within:border-blue-500 transition-all">
              <button
                onClick={isRecording ? stopRecording : startRecording}
                disabled={isProcessing}
                className={`p-4 rounded-none md:rounded-2xl transition-all flex-shrink-0 ${isRecording
                  ? 'bg-rose-600 text-white animate-pulse shadow-lg'
                  : isProcessing
                    ? 'bg-blue-100 text-blue-600 cursor-wait'
                    : 'bg-slate-50 text-slate-400 hover:text-blue-600 hover:bg-blue-50'
                  }`}
              >
                {isProcessing ? (
                  // Spinner de Carregamento
                  <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                ) : isRecording ? (
                  // Ícone de Parar (Quadrado)
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
                ) : (
                  // Ícone de Microfone
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                )}
              </button>

              <input
                type="text"
                disabled={isRecording || isProcessing}
                placeholder={
                  isRecording
                    ? "Gravando... Fale agora para transcrever."
                    : isProcessing
                      ? "Hermes AI está processando seu áudio..."
                      : "Digite ou grave uma nova nota..."
                }
                className={`flex-1 bg-transparent border-none outline-none px-2 py-4 text-sm font-bold text-slate-800 placeholder:text-slate-300 ${(isRecording || isProcessing) ? 'opacity-50' : ''}`}
                value={textInput}
                onChange={e => setTextInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && textInput.trim()) {
                    onAddTextIdea(textInput);
                    setTextInput('');
                  }
                }}
              />
              <button
                onClick={() => {
                  if (textInput.trim()) {
                    onAddTextIdea(textInput);
                    setTextInput('');
                  }
                }}
                className="bg-blue-600 text-white h-12 w-12 flex items-center justify-center rounded-lg md:rounded-2xl hover:bg-blue-700 transition-all shadow-lg shadow-blue-100 active:scale-95 shrink-0"
                title="Salvar Nota"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
              </button>
            </div>
          </div>
        </div>

        <div className="flex flex-col md:grid md:grid-cols-2 lg:grid-cols-3 gap-0 md:gap-8 mb-32 md:mb-0">
          {activeIdeas.map(idea => (
            <div key={idea.id} className="bg-white p-5 md:p-8 rounded-none md:rounded-[2.5rem] border border-slate-100 md:border-slate-200 shadow-none md:shadow-lg hover:shadow-none md:hover:shadow-2xl transition-all group flex flex-col relative overflow-hidden -ml-px -mt-px md:m-0">
              <div className="flex items-center justify-between mb-3 md:mb-6">
                <span className="text-[9px] md:text-[10px] font-black text-slate-400 uppercase tracking-widest">{formatDate(idea.timestamp.split('T')[0])}</span>
                <div className="flex items-center gap-1 md:gap-2 opacity-100 md:opacity-0 group-hover:opacity-100 transition-all">
                  {editingId === idea.id ? (
                    <button
                      onClick={() => {
                        if (editText.trim()) {
                          onUpdateIdea(idea.id, editText);
                          setEditingId(null);
                        }
                      }}
                      className="text-blue-600 hover:bg-blue-50 p-2 rounded-lg md:rounded-xl transition-colors"
                    >
                      <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={() => {
                          setEditingId(idea.id);
                          setEditText(idea.text);
                        }}
                        className="text-slate-400 hover:text-blue-600 p-2 rounded-lg md:rounded-xl transition-colors"
                        title="Editar"
                      >
                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                      </button>
                      <button
                        onClick={() => onConvertToLog(idea)}
                        className="text-slate-400 hover:text-violet-600 p-2 rounded-lg md:rounded-xl transition-colors"
                        title="Converter em Log"
                      >
                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                      </button>
                      <button
                        onClick={() => onConvertToTask(idea)}
                        className="text-slate-400 hover:text-sky-600 p-2 rounded-lg md:rounded-xl transition-colors"
                        title="Converter em Ação"
                      >
                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                      </button>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(idea.text).then(() => {
                            setCopiedId(idea.id);
                            setTimeout(() => setCopiedId(null), 2000);
                          });
                        }}
                        className={`p-2 rounded-lg md:rounded-xl transition-colors ${copiedId === idea.id ? 'text-emerald-500 bg-emerald-50' : 'text-slate-400 hover:text-blue-600'}`}
                        title="Copiar Texto"
                      >
                        {copiedId === idea.id ? (
                          <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                        ) : (
                          <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>
                        )}
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => onArchiveIdea(idea.id)}
                    className="text-emerald-500 hover:bg-emerald-50 p-2 rounded-lg md:rounded-xl transition-colors"
                    title="Concluir / Arquivar"
                  >
                    <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                  </button>
                  <button
                    onClick={() => {
                      if (confirmDeleteId === idea.id) {
                        onDeleteIdea(idea.id);
                        setConfirmDeleteId(null);
                      } else {
                        setConfirmDeleteId(idea.id);
                        setTimeout(() => setConfirmDeleteId(null), 3000);
                      }
                    }}
                    className={`p-2 rounded-lg md:rounded-xl transition-colors ${confirmDeleteId === idea.id ? 'bg-rose-500 text-white shadow-md' : 'text-slate-300 hover:text-rose-500'}`}
                    title="Excluir Permanentemente"
                  >
                    {confirmDeleteId === idea.id ? (
                      <svg className="w-4 h-4 md:w-5 md:h-5 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                    ) : (
                      <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                    )}
                  </button>
                </div>
              </div>

              {editingId === idea.id ? (
                <AutoExpandingTextarea
                  autoFocus
                  className="w-full bg-slate-50 border border-slate-200 rounded-none md:rounded-2xl p-4 text-sm md:text-lg font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500 min-h-[100px]"
                  value={editText}
                  onChange={e => setEditText(e.target.value)}
                />
              ) : (
                <div className="flex-1">
                  <p
                    className={`text-slate-800 font-bold leading-relaxed mb-3 md:mb-6 text-sm md:text-lg ${!expandedCards.has(idea.id) && idea.text.length > 150 ? 'line-clamp-3' : ''
                      }`}
                  >
                    "{idea.text}"
                  </p>
                  {idea.text.length > 150 && (
                    <button
                      onClick={() => toggleCardExpansion(idea.id)}
                      className="text-blue-600 hover:text-blue-700 text-xs font-black uppercase tracking-widest transition-colors flex items-center gap-1"
                    >
                      {expandedCards.has(idea.id) ? (
                        <>
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 15l7-7 7 7" /></svg>
                          Mostrar menos
                        </>
                      ) : (
                        <>
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" /></svg>
                          Mostrar mais
                        </>
                      )}
                    </button>
                  )}
                </div>
              )}

              {idea.audioUrl && (
                <audio controls src={idea.audioUrl} className="w-full h-10 opacity-50 hover:opacity-100 transition-opacity" />
              )}
            </div>
          ))}
          {activeIdeas.length === 0 && !isProcessing && (
            <div className="col-span-full py-20 text-center border-4 border-dashed border-slate-100 rounded-none md:rounded-none md:rounded-[3rem]">
              <p className="text-slate-300 font-black text-xl uppercase tracking-widest">Nenhuma nota ativa</p>
              <p className="text-slate-400 text-sm font-medium mt-2">Grave ou digite uma nota para começar.</p>
            </div>
          )}
        </div>

        {/* Seção Retrátil de Ideias Arquivadas */}
        <div className="mt-12 space-y-6">
          <button
            onClick={() => setIsArchivedIdeasOpen(!isArchivedIdeasOpen)}
            className="w-full flex items-center gap-4 group cursor-pointer"
          >
            <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
            <div className="flex items-center gap-2 text-slate-400 group-hover:text-slate-600 transition-colors">
              <h3 className="text-[10px] font-black uppercase tracking-[0.3em]">Notas Arquivadas</h3>
              <svg className={`w-4 h-4 transition-transform duration-300 ${isArchivedIdeasOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
              </svg>
            </div>
            <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
          </button>

          {isArchivedIdeasOpen && (
            <div className="flex flex-col md:grid md:grid-cols-2 lg:grid-cols-3 gap-0 md:gap-8 opacity-60 hover:opacity-100 transition-opacity animate-in slide-in-from-top-4 duration-300">
              {archivedIdeas.map(idea => (
                <div key={idea.id} className="bg-white p-5 md:p-8 rounded-none md:rounded-[2.5rem] border border-slate-100 md:border-slate-200 shadow-none md:shadow-lg hover:shadow-none md:hover:shadow-2xl transition-all group flex flex-col relative overflow-hidden -ml-px -mt-px md:m-0">
                  <div className="flex items-center justify-between mb-3 md:mb-6">
                    <span className="text-[9px] md:text-[10px] font-black text-slate-400 uppercase tracking-widest">{formatDate(idea.timestamp.split('T')[0])}</span>
                    <div className="flex items-center gap-1 md:gap-2 opacity-100 md:opacity-0 group-hover:opacity-100 transition-all">
                      <button
                        onClick={() => onArchiveIdea(idea.id)}
                        className="text-blue-500 hover:bg-blue-50 p-2 rounded-lg md:rounded-xl transition-colors"
                        title="Restaurar Ideia"
                      >
                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg>
                      </button>
                      <button
                        onClick={() => {
                          if (confirmDeleteId === idea.id) {
                            onDeleteIdea(idea.id);
                            setConfirmDeleteId(null);
                          } else {
                            setConfirmDeleteId(idea.id);
                            setTimeout(() => setConfirmDeleteId(null), 3000);
                          }
                        }}
                        className={`p-2 rounded-lg md:rounded-xl transition-colors ${confirmDeleteId === idea.id ? 'bg-rose-500 text-white shadow-md' : 'text-slate-300 hover:text-rose-500'}`}
                        title="Excluir Permanentemente"
                      >
                        {confirmDeleteId === idea.id ? (
                          <svg className="w-4 h-4 md:w-5 md:h-5 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                        ) : (
                          <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                        )}
                      </button>
                    </div>
                  </div>

                  <div className="flex-1">
                    <p className="text-slate-500 font-bold italic leading-relaxed mb-3 md:mb-6 text-sm md:text-lg line-clamp-3">
                      "{idea.text}"
                    </p>
                  </div>
                </div>
              ))}
              {archivedIdeas.length === 0 && (
                <div className="col-span-full py-12 text-center">
                  <p className="text-slate-300 font-black text-[10px] uppercase tracking-widest italic">Nenhuma nota arquivada</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Input Flutuante Centralizado */}
      {isAddingText && (
        <div className="fixed bottom-24 left-4 right-4 md:left-1/2 md:-translate-x-1/2 w-auto md:w-full md:max-w-2xl z-[110] flex items-center gap-2 animate-in zoom-in-95 slide-in-from-bottom-10 bg-white/90 backdrop-blur-md p-4 rounded-none md:rounded-[2rem] shadow-2xl border border-slate-200">
          <button
            onClick={isRecording ? stopRecording : startRecording}
            className={`p-4 rounded-none md:rounded-2xl transition-all shadow-xl flex-shrink-0 ${isRecording
              ? 'bg-rose-600 text-white animate-pulse shadow-rose-200'
              : 'bg-white text-slate-400 hover:text-blue-600 border border-slate-200'
              }`}
          >
            {isRecording ? (
              // Ícone de Parar (Quadrado)
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
            ) : (
              // Ícone de Microfone
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
            )}
          </button>

          <input
            type="text"
            disabled={isRecording}
            autoFocus
            placeholder={isRecording ? "Gravando... Fale agora." : "Digite ou grave sua nota..."}
            className={`flex-1 bg-white border border-slate-200 rounded-none md:rounded-2xl px-6 py-4 text-sm font-medium focus:ring-4 focus:ring-blue-100 outline-none shadow-sm transition-all ${isRecording ? 'opacity-50' : ''}`}
            value={textInput}
            onChange={e => setTextInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && textInput.trim()) {
                onAddTextIdea(textInput);
                setTextInput('');
                setIsAddingText(false);
              }
            }}
          />
          <button
            onClick={() => {
              if (textInput.trim()) {
                onAddTextIdea(textInput);
                setTextInput('');
                setIsAddingText(false);
              } else {
                setIsAddingText(false);
              }
            }}
            className="bg-blue-600 text-white p-4 rounded-none md:rounded-2xl hover:bg-blue-700 transition-all shadow-xl shadow-blue-100 flex-shrink-0"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
          </button>
        </div>
      )}

    </>
  );
};

const getBucketStartDate = (label: string): string => {
  const now = new Date();
  now.setHours(0, 0, 0, 0);

  if (label === 'Hoje') return now.toLocaleDateString('en-CA');

  if (label === 'Amanhã') {
    const d = new Date(now);
    d.setDate(d.getDate() + 1);
    return d.toLocaleDateString('en-CA');
  }

  if (label === 'Esta Semana') {
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const d = new Date(tomorrow);
    d.setDate(d.getDate() + 1);
    return d.toLocaleDateString('en-CA');
  }

  if (label === 'Este Mês') {
    const endOfWeek = new Date(now);
    endOfWeek.setDate(now.getDate() + (6 - now.getDay()));
    const d = new Date(endOfWeek);
    d.setDate(d.getDate() + 1);
    return d.toLocaleDateString('en-CA');
  }

  const meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
  const lowerLabel = label.toLowerCase();

  const mesIndex = meses.findIndex(m => lowerLabel.includes(m));
  if (mesIndex >= 0) {
    const anoMatch = lowerLabel.match(/\d{4}/);
    if (anoMatch) {
      const ano = parseInt(anoMatch[0]);
      const d = new Date(ano, mesIndex, 1);
      return d.toLocaleDateString('en-CA');
    }
  }

  if (label === 'Atrasadas') {
    const d = new Date(now);
    d.setDate(d.getDate() - 1);
    return d.toLocaleDateString('en-CA');
  }

  return '';
};

// ─────────────────────────────────────────────────────────────────────────────

const QuickNoteModal = ({ isOpen, onClose, onAddIdea, showAlert }: { isOpen: boolean, onClose: () => void, onAddIdea: (text: string) => void, showAlert: (t: string, m: string) => void }) => {
  const [textInput, setTextInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  if (!isOpen) return null;

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/m4a' });
        await handleProcessAudio(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };
      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Erro ao acessar microfone:", err);
      showAlert("Erro", "Permissão de microfone negada ou não disponível.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleProcessAudio = async (audioBlob: Blob) => {
    setIsProcessing(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String });
          const data = response.data as { raw: string, refined: string };
          if (data.refined) onAddIdea(data.refined);
        } catch (error) {
          console.error("Erro ao transcrever:", error);
          showAlert("Erro", "Erro ao processar áudio via Hermes AI.");
        } finally {
          setIsProcessing(false);
        }
      };
    } catch (error) {
      console.error("Erro ao ler áudio:", error);
      setIsProcessing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[250] flex items-center justify-center p-4 bg-slate-900/60 animate-in fade-in">
      <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div>
            <h3 className="text-2xl font-black text-slate-900 tracking-tight">Nota Rápida</h3>
            <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest mt-1">Captação Instantânea</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="p-8 space-y-6">
          <div className="bg-slate-50 p-2 rounded-none md:rounded-2xl border-2 border-slate-100 flex items-center gap-4 focus-within:border-blue-500 transition-all">
            <button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isProcessing}
              className={`p-4 rounded-none md:rounded-xl transition-all flex-shrink-0 ${isRecording
                ? 'bg-rose-600 text-white animate-pulse shadow-lg'
                : isProcessing
                  ? 'bg-blue-100 text-blue-600 cursor-wait'
                  : 'bg-white border border-slate-200 text-slate-400 hover:text-blue-600'
                }`}
            >
              {isProcessing ? (
                <div className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
              ) : isRecording ? (
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
              )}
            </button>
            <input
              autoFocus
              type="text"
              disabled={isRecording || isProcessing}
              placeholder={isRecording ? "Gravando..." : isProcessing ? "Processando..." : "O que está pensando?"}
              className="flex-1 bg-transparent border-none outline-none py-4 text-base font-bold text-slate-800 placeholder:text-slate-300"
              value={textInput}
              onChange={e => setTextInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && textInput.trim()) {
                  onAddIdea(textInput);
                  setTextInput('');
                  onClose();
                }
              }}
            />
          </div>
          <div className="flex gap-4">
            <button onClick={onClose} className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-2xl transition-all">Cancelar</button>
            <button
              onClick={() => {
                if (textInput.trim()) {
                  onAddIdea(textInput);
                  setTextInput('');
                  onClose();
                }
              }}
              disabled={!textInput.trim()}
              className="flex-none w-12 md:w-auto md:flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5 md:hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
              <span className="hidden md:inline">Salvar Ideia</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

const QuickLogModal = ({ isOpen, onClose, onAddLog, unidades }: { isOpen: boolean, onClose: () => void, onAddLog: (text: string, systemId: string) => void, unidades: { id: string, nome: string }[] }) => {
  const [textInput, setTextInput] = useState('');
  const [selectedSystem, setSelectedSystem] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const systems = useMemo(() => unidades.filter(u => u.nome.startsWith('SISTEMA:')), [unidades]);

  useEffect(() => {
    if (systems.length > 0 && !selectedSystem) {
      setSelectedSystem(systems[0].id);
    }
  }, [systems, selectedSystem]);

  if (!isOpen) return null;

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/m4a' });
        await handleProcessAudio(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };
      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Erro ao acessar microfone:", err);
      alert("Permissão de microfone negada ou não disponível.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleProcessAudio = async (audioBlob: Blob) => {
    setIsProcessing(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String });
          const data = response.data as { raw: string, refined: string };
          if (data.refined) {
            const newText = textInput ? textInput + '\n' + data.refined : data.refined;
            setTextInput(newText);
          }
        } catch (error) {
          console.error("Erro ao transcrever:", error);
          alert("Erro ao processar áudio via Hermes AI.");
        } finally {
          setIsProcessing(false);
        }
      };
    } catch (error) {
      console.error("Erro ao ler áudio:", error);
      setIsProcessing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[250] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in">
      <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div>
            <h3 className="text-2xl font-black text-slate-900 tracking-tight">Log Rápido</h3>
            <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest mt-1">Registro de Sistema</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="p-8 space-y-6">
          <div className="space-y-2">
            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Sistema</label>
            <select
              value={selectedSystem}
              onChange={(e) => setSelectedSystem(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 rounded-lg md:rounded-xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-violet-500"
            >
              <option value="" disabled>Selecione um sistema</option>
              {systems.map(s => (
                <option key={s.id} value={s.id}>{s.nome.replace('SISTEMA:', '').trim()}</option>
              ))}
            </select>
          </div>

          <div className="bg-slate-50 p-2 rounded-none md:rounded-2xl border-2 border-slate-100 flex items-center gap-4 focus-within:border-violet-500 transition-all">
            <button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isProcessing}
              className={`p-4 rounded-none md:rounded-xl transition-all flex-shrink-0 ${isRecording
                ? 'bg-rose-600 text-white animate-pulse shadow-lg'
                : isProcessing
                  ? 'bg-violet-100 text-violet-600 cursor-wait'
                  : 'bg-white border border-slate-200 text-slate-400 hover:text-violet-600'
                }`}
            >
              {isProcessing ? (
                <div className="w-5 h-5 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
              ) : isRecording ? (
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
              )}
            </button>
            <input
              autoFocus
              type="text"
              disabled={isRecording || isProcessing}
              placeholder={isRecording ? "Gravando..." : isProcessing ? "Processando..." : "Descreva o ajuste..."}
              className="flex-1 bg-transparent border-none outline-none py-4 text-base font-bold text-slate-800 placeholder:text-slate-300"
              value={textInput}
              onChange={e => setTextInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && textInput.trim() && selectedSystem) {
                  onAddLog(textInput, selectedSystem);
                  setTextInput('');
                  onClose();
                }
              }}
            />
          </div>
          <div className="flex gap-4">
            <button onClick={onClose} className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-2xl transition-all">Cancelar</button>
            <button
              onClick={() => {
                if (textInput.trim() && selectedSystem) {
                  onAddLog(textInput, selectedSystem);
                  setTextInput('');
                  onClose();
                }
              }}
              disabled={!textInput.trim() || !selectedSystem}
              className="flex-none w-16 md:w-auto md:flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5 md:hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
              <span className="hidden md:inline">Registrar Log</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

const TranscriptionAIModal = ({ isOpen, onClose, showToast }: { isOpen: boolean, onClose: () => void, showToast: (m: string, t: 'success' | 'error' | 'info') => void }) => {
  const [file, setFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [transcription, setTranscription] = useState<{ raw: string, refined: string } | null>(null);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setFile(null);
      setTranscription(null);
      return;
    }

    const handlePaste = (e: ClipboardEvent) => {
      if (e.clipboardData && e.clipboardData.files.length > 0) {
        const pastedFile = e.clipboardData.files[0];
        if (pastedFile.type.startsWith('audio/') || pastedFile.type.startsWith('video/')) {
          handleFileSelection(pastedFile);
        }
      }
    };
    window.addEventListener('paste', handlePaste);
    return () => window.removeEventListener('paste', handlePaste);
  }, [isOpen]);

  const handleFileSelection = (f: File) => {
    if (f.size > 25 * 1024 * 1024) {
      if (f.size > 6 * 1024 * 1024) {
        showToast("Arquivo muito grande. Limite: 6MB.", "error");
        return;
      }
    }
    setFile(f);
    setTranscription(null);
  };

  const handleTranscribe = async () => {
    if (!file) return;
    setIsProcessing(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];
          const extension = `.${file.name.split('.').pop()?.toLowerCase() || 'm4a'}`;
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String, extension });
          const data = response.data as { raw: string, refined: string };
          setTranscription(data);
          
          // Also save to history for compatibility with the tool
          const saved = localStorage.getItem('hermes_transcription_history');
          const history = saved ? JSON.parse(saved) : [];
          const newEntry = {
            id: Date.now().toString(),
            fileName: file.name,
            fileSize: file.size,
            date: new Date().toISOString(),
            raw: data.raw,
            refined: data.refined
          };
          localStorage.setItem('hermes_transcription_history', JSON.stringify([newEntry, ...history].slice(0, 50)));

          showToast("Transcrição concluída!", "success");
        } catch (error) {
          console.error(error);
          showToast("Erro ao processar áudio.", "error");
        } finally {
          setIsProcessing(false);
        }
      };
    } catch (e) {
      setIsProcessing(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[250] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in">
      <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div>
            <h3 className="text-2xl font-black text-slate-900 tracking-tight">Transcrição Rápida</h3>
            <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest mt-1">IA Audio Processing</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="p-8 space-y-6">
          {!transcription ? (
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={e => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files.length) handleFileSelection(e.dataTransfer.files[0]); }}
              className={`border-4 border-dashed rounded-none md:rounded-[2rem] p-10 flex flex-col items-center justify-center text-center gap-4 transition-all ${dragOver ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 bg-slate-50'}`}
            >
              {isProcessing ? (
                <div className="flex flex-col items-center gap-4 py-10">
                  <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
                  <p className="text-indigo-600 font-black uppercase tracking-widest text-[10px]">Processando seu áudio...</p>
                </div>
              ) : file ? (
                <div className="space-y-4 py-4 w-full">
                  <div className="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto">
                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
                  </div>
                  <p className="text-lg font-black text-slate-900 truncate px-4">{file.name}</p>
                  <button onClick={handleTranscribe} className="bg-indigo-600 text-white px-8 py-3 rounded-none md:rounded-2xl font-black uppercase tracking-widest text-[10px] shadow-lg hover:bg-indigo-700 transition-all">Transcrever Agora</button>
                </div>
              ) : (
                <div className="py-10">
                  <div className="w-16 h-16 bg-slate-200 text-slate-400 rounded-full flex items-center justify-center mx-auto mb-4">
                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
                  </div>
                  <div className="space-y-1">
                    <p className="font-black text-slate-900">Cole seu áudio aqui (Ctrl+V)</p>
                    <p className="text-slate-400 text-xs font-medium">Ou arraste o arquivo aqui</p>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-6 animate-in slide-in-from-bottom-4">
              <div className="bg-slate-50 p-6 rounded-none md:rounded-[2rem] border border-slate-100 max-h-[300px] overflow-y-auto custom-scrollbar">
                <label className="text-[10px] font-black text-indigo-500 uppercase tracking-widest block mb-2">Resultado Final</label>
                <p className="text-slate-800 text-base font-bold leading-relaxed whitespace-pre-wrap">{transcription.refined}</p>
              </div>
              <div className="flex gap-4">
                <button
                  onClick={() => { navigator.clipboard.writeText(transcription.refined); showToast("Texto copiado!", "success"); }}
                  className="flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-indigo-600 transition-all flex items-center justify-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                  Copiar Texto
                </button>
                <button onClick={() => setTranscription(null)} className="px-8 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-2xl transition-all">Novo</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

interface AIMatchedItem {
  id: string;
  nome: string;
  categoria: string;
  quantidade: string;
  unit: string;
  confirmed: boolean; // user can uncheck
  isNew?: boolean;    // not in catalog yet
}

const ShoppingAIModal = ({
  isOpen, onClose, catalogItems, onConfirmItems, onViewList
}: {
  isOpen: boolean;
  onClose: () => void;
  catalogItems: ShoppingItem[];
  onConfirmItems: (items: { id: string; quantidade: string }[]) => void;
  onViewList: () => void;
}) => {
  const [step, setStep] = useState<'input' | 'processing' | 'validation'>('input');
  const [textInput, setTextInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [matchedItems, setMatchedItems] = useState<AIMatchedItem[]>([]);
  const [errorMsg, setErrorMsg] = useState('');
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const resetToInput = () => { setStep('input'); setMatchedItems([]); setErrorMsg(''); };

  if (!isOpen) return null;

  // --- Recording ---
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      audioChunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mr.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/m4a' });
        stream.getTracks().forEach(t => t.stop());
        // Transcribe then process
        setStep('processing');
        try {
          const reader = new FileReader();
          reader.readAsDataURL(blob);
          reader.onloadend = async () => {
            try {
              const base64 = (reader.result as string).split(',')[1];
              const fn = httpsCallable(functions, 'transcreverAudio');
              const res = await fn({ audioBase64: base64 });
              const data = res.data as { refined: string };
              const transcript = data.refined || '';
              if (transcript) {
                await processWithGemini(transcript);
              } else {
                setErrorMsg('Não consegui transcrever o áudio. Tente digitar.');
                setStep('input');
              }
            } catch {
              setErrorMsg('Erro ao transcrever áudio.');
              setStep('input');
            }
          };
        } catch {
          setErrorMsg('Erro ao ler áudio.');
          setStep('input');
        }
      };
      mr.start();
      setIsRecording(true);
    } catch {
      alert('Permissão de microfone negada.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  // --- Gemini matching ---
  const processWithGemini = async (text: string) => {
    setStep('processing');
    setErrorMsg('');
    try {
      const catalog = catalogItems.map(i => `ID:${i.id}|NOME:${i.nome}|CAT:${i.categoria}`).join('\n');
      const prompt = `Você é um assistente de lista de compras. O usuário descreveu itens que deseja comprar.

CATÁLOGO DISPONÍVEL (id|nome|categoria):
${catalog || '(vazio)'}

PEDIDO DO USUÁRIO:
"${text}"

Sua tarefa:
1. Para cada item mencionado pelo usuário, encontre o item mais próximo no catálogo (matching fuzzy/semântico tolerante a abreviações, sinônimos e erros). Ex: "ricota" pode corresponder a "Queijo Ricota".
2. Identifique a quantidade mencionada (número + unidade se houver). Se não mencionado, use "1 un".
3. Se não houver correspondência razoável no catálogo, marque isNew=true com o nome como o usuário falou.

Responda SOMENTE com JSON válido no formato abaixo, sem markdown, sem explicações:
{
  "itens": [
    { "catalogId": "ID_DO_ITEM_OU_null_SE_NOVO", "nomeExibido": "Nome para exibir", "quantidade": "2", "unit": "kg", "isNew": false }
  ]
}`;

      let apiKey = process.env.GEMINI_API_KEY || import.meta.env.VITE_GEMINI_API_KEY || '';

      if (!apiKey) {
        try {
          const keyDoc = await getDoc(doc(db, 'system', 'api_keys'));
          if (keyDoc.exists()) {
            apiKey = keyDoc.data()?.gemini_api_key || '';
          }
        } catch (e) {
          console.error("Erro ao buscar chave de API:", e);
        }
      }

      if (!apiKey) {
        setErrorMsg('Chave do Gemini não configurada no Firestore.');
        setStep('input');
        return;
      }

      const genAI = new GoogleGenerativeAI(apiKey);
      const model = genAI.getGenerativeModel({ model: 'gemini-2.5-flash' });
      const result = await model.generateContent(prompt);
      const raw = result.response.text().trim();

      // Parse JSON (strip possible markdown fences)
      const jsonStr = raw.replace(/^```json\s*/i, '').replace(/^```\s*/i, '').replace(/```\s*$/i, '').trim();
      const parsed = JSON.parse(jsonStr);

      const resolved: AIMatchedItem[] = (parsed.itens || []).map((it: any) => {
        const catalogItem = it.catalogId ? catalogItems.find(c => c.id === it.catalogId) : null;
        return {
          id: catalogItem?.id || `new_${Date.now()}_${Math.random()}`,
          nome: it.nomeExibido || catalogItem?.nome || 'Item desconhecido',
          categoria: catalogItem?.categoria || 'Geral',
          quantidade: String(it.quantidade || '1'),
          unit: it.unit || 'un',
          confirmed: true,
          isNew: !!it.isNew || !catalogItem,
        };
      });

      if (resolved.length === 0) {
        setErrorMsg('Não identifiquei itens no pedido. Tente descrever de forma diferente.');
        setStep('input');
        return;
      }

      setMatchedItems(resolved);
      setStep('validation');
    } catch (e) {
      console.error(e);
      setErrorMsg('Erro ao processar com IA. Verifique a conexão.');
      setStep('input');
    }
  };

  const handleSubmitText = async () => {
    if (!textInput.trim()) return;
    await processWithGemini(textInput.trim());
  };

  const toggleItem = (id: string) => {
    setMatchedItems(prev => prev.map(i => i.id === id ? { ...i, confirmed: !i.confirmed } : i));
  };

  const updateQtd = (id: string, val: string) => {
    setMatchedItems(prev => prev.map(i => i.id === id ? { ...i, quantidade: val } : i));
  };

  const handleConfirm = () => {
    const toAdd = matchedItems.filter(i => i.confirmed && !i.isNew);
    if (toAdd.length === 0) { onClose(); return; }
    onConfirmItems(toAdd.map(i => ({ id: i.id, quantidade: i.quantidade })));
    setTextInput('');
    setMatchedItems([]);
    setStep('input');
    onClose();
  };

  const confirmedCount = matchedItems.filter(i => i.confirmed && !i.isNew).length;
  const newCount = matchedItems.filter(i => i.isNew).length;

  return (
    <div className="fixed inset-0 z-[250] flex items-center justify-center p-0 md:p-4 bg-slate-900/70 backdrop-blur-md animate-in fade-in">
      <div className="bg-white w-full max-w-2xl h-full md:h-auto md:max-h-[92vh] rounded-none md:rounded-[2.5rem] shadow-[0_40px_80px_-20px_rgba(0,0,0,0.35)] flex flex-col overflow-hidden animate-in zoom-in-95 duration-300">

        {/* Header */}
        <div className="p-7 md:p-8 border-b border-slate-100 bg-gradient-to-br from-emerald-50/80 to-white flex items-center gap-4 flex-shrink-0">
          <div className="w-12 h-12 bg-emerald-600 rounded-2xl flex items-center justify-center shadow-lg shadow-emerald-200 flex-shrink-0">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-xl font-black text-slate-900 tracking-tight">Assistente de Compras IA</h3>
            <p className="text-emerald-600 text-[10px] font-black uppercase tracking-[0.2em] mt-0.5">
              {step === 'input' ? 'Diga o que você quer comprar' : step === 'processing' ? 'Buscando no catálogo...' : 'Valide os itens identificados'}
            </p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-2xl transition-all flex-shrink-0">
            <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-7 md:p-8 space-y-5">

          {/* === INPUT STEP === */}
          {step === 'input' && (
            <>
              {errorMsg && (
                <div className="bg-rose-50 border border-rose-100 rounded-2xl px-5 py-3 flex items-center gap-3">
                  <svg className="w-4 h-4 text-rose-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                  <p className="text-rose-700 text-sm font-bold">{errorMsg}</p>
                </div>
              )}

              <div className="bg-slate-50 rounded-[2rem] border-2 border-slate-100 focus-within:border-emerald-400 transition-all shadow-inner overflow-hidden">
                <div className="flex items-start gap-3 p-4">
                  <button
                    onClick={isRecording ? stopRecording : startRecording}
                    className={`mt-1 w-12 h-12 rounded-2xl flex items-center justify-center flex-shrink-0 transition-all ${isRecording ? 'bg-rose-500 text-white animate-pulse shadow-lg shadow-rose-200' : 'bg-white border border-slate-200 text-slate-400 hover:text-emerald-600 hover:border-emerald-200 hover:shadow-md'}`}
                    title={isRecording ? 'Parar gravação' : 'Gravar áudio'}
                  >
                    {isRecording
                      ? <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
                      : <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>}
                  </button>
                  <textarea
                    autoFocus
                    className="flex-1 bg-transparent border-none outline-none py-3 text-base font-bold text-slate-800 placeholder:text-slate-300 resize-none min-h-[120px]"
                    placeholder={isRecording ? '🎙️ Gravando... Fale os itens que deseja comprar...' : 'Ex: "2 kg de arroz, 1 caixa de leite, ricota, sabão em pó e 3 iogurtes"'}
                    value={textInput}
                    disabled={isRecording}
                    onChange={e => setTextInput(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) handleSubmitText(); }}
                  />
                </div>
                {isRecording && (
                  <div className="px-5 pb-4 flex items-center gap-2">
                    <div className="flex gap-0.5">
                      {[...Array(8)].map((_, i) => (
                        <div key={i} className="w-1 bg-rose-500 rounded-full animate-pulse" style={{ height: `${8 + Math.random() * 16}px`, animationDelay: `${i * 100}ms` }} />
                      ))}
                    </div>
                    <span className="text-rose-600 text-[11px] font-black uppercase tracking-widest">Gravando</span>
                  </div>
                )}
              </div>

              <div className="bg-emerald-50/60 rounded-2xl border border-emerald-100/60 px-5 py-4 flex gap-3">
                <svg className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                <p className="text-[11px] font-bold text-emerald-800 leading-relaxed">
                  O Hermes vai buscar os itens no seu catálogo usando IA. "Ricota" pode corresponder a "Queijo Ricota", "Bombril" a "Palha de Aço", etc.
                </p>
              </div>
            </>
          )}

          {/* === PROCESSING STEP === */}
          {step === 'processing' && (
            <div className="py-20 flex flex-col items-center justify-center gap-6 text-center">
              <div className="relative w-20 h-20">
                <div className="w-20 h-20 rounded-full border-4 border-emerald-100 animate-spin border-t-emerald-500" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <svg className="w-8 h-8 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                </div>
              </div>
              <div>
                <p className="font-black text-slate-800 text-lg">Hermes está pensando...</p>
                <p className="text-slate-400 text-sm font-medium mt-1">Buscando correspondências no catálogo</p>
              </div>
            </div>
          )}

          {/* === VALIDATION STEP === */}
          {step === 'validation' && (
            <div className="space-y-4 animate-in fade-in duration-300">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-black text-slate-800">{matchedItems.filter(i => !i.isNew).length} itens identificados</p>
                  {newCount > 0 && <p className="text-[10px] text-amber-600 font-black uppercase tracking-widest mt-0.5">{newCount} não encontrado{newCount > 1 ? 's' : ''} no catálogo</p>}
                </div>
                <button onClick={resetToInput} className="text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-slate-700 transition-colors">
                  ← Refazer
                </button>
              </div>

              <div className="space-y-2">
                {matchedItems.map(item => (
                  <div
                    key={item.id}
                    onClick={() => !item.isNew && toggleItem(item.id)}
                    className={`rounded-2xl border px-5 py-4 flex items-center gap-4 transition-all ${item.isNew ? 'bg-amber-50/50 border-amber-100 opacity-60 cursor-not-allowed' : item.confirmed ? 'bg-emerald-50/40 border-emerald-200 cursor-pointer hover:bg-emerald-50' : 'bg-slate-50 border-slate-100 cursor-pointer opacity-50 hover:opacity-70'}`}
                  >
                    {/* Checkbox */}
                    <div className={`w-7 h-7 rounded-xl border-2 flex items-center justify-center flex-shrink-0 transition-all ${item.isNew ? 'border-amber-300 bg-amber-100' : item.confirmed ? 'bg-emerald-500 border-emerald-500 text-white' : 'border-slate-300 bg-white'}`}>
                      {item.isNew
                        ? <svg className="w-3.5 h-3.5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01" /></svg>
                        : item.confirmed ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                          : null}
                    </div>

                    {/* Item info */}
                    <div className="flex-1 min-w-0">
                      <p className={`font-black text-sm truncate ${item.isNew ? 'text-amber-700' : 'text-slate-900'}`}>{item.nome}</p>
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">
                        {item.isNew ? '⚠ Não no catálogo' : item.categoria}
                      </p>
                    </div>

                    {/* Quantity editor */}
                    {!item.isNew && (
                      <div onClick={e => e.stopPropagation()} className="flex items-center gap-2 bg-white border border-slate-100 rounded-xl px-3 py-2 shadow-sm">
                        <button onClick={() => updateQtd(item.id, String(Math.max(0.5, parseFloat(item.quantidade) - 1)))} className="w-5 h-5 rounded-lg bg-slate-100 font-black flex items-center justify-center text-slate-600 hover:bg-emerald-100 transition-all text-sm leading-none">−</button>
                        <span className="w-12 text-center font-black text-slate-800 text-sm">
                          {item.quantidade} <span className="text-slate-400 font-medium text-[10px]">{item.unit}</span>
                        </span>
                        <button onClick={() => updateQtd(item.id, String(parseFloat(item.quantidade) + 1))} className="w-5 h-5 rounded-lg bg-slate-100 font-black flex items-center justify-center text-slate-600 hover:bg-emerald-100 transition-all text-sm leading-none">+</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {newCount > 0 && (
                <div className="bg-amber-50 border border-amber-100 rounded-2xl px-5 py-3 flex gap-3">
                  <svg className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                  <p className="text-[11px] font-bold text-amber-800 leading-relaxed">
                    {newCount} item(ns) não foram encontrados no catálogo. Cadastre-os primeiro na aba "Cadastro" e o assistente os reconhecerá na próxima vez.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex-shrink-0 p-6 md:p-8 pt-0 space-y-3">
          {step === 'input' && (
            <div className="flex gap-4">
              <button onClick={onClose} className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-2xl transition-all">Fechar</button>
              <button
                onClick={handleSubmitText}
                disabled={!textInput.trim() || isRecording}
                className="flex-[2] bg-emerald-600 text-white py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg shadow-emerald-100 hover:bg-emerald-700 transition-all disabled:opacity-50 disabled:grayscale flex items-center justify-center gap-2 active:scale-[0.98]"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                Processar com IA
              </button>
            </div>
          )}

          {step === 'validation' && (
            <div className="flex gap-4">
              <button onClick={resetToInput} className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-2xl transition-all">Voltar</button>
              <button
                onClick={handleConfirm}
                disabled={confirmedCount === 0}
                className="flex-[2] bg-slate-900 text-white py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-xl hover:bg-emerald-600 transition-all disabled:opacity-50 disabled:grayscale flex items-center justify-center gap-2 active:scale-[0.98]"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                Confirmar {confirmedCount} iten{confirmedCount !== 1 ? 's' : ''}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const App: React.FC = () => {
  // Public Route Interception
  if (window.location.pathname.startsWith('/join/')) {
    return <PublicScholarshipRegistration />;
  }

  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [rememberMe, setRememberMe] = useState(true);
  const [tarefas, setTarefas] = useState<Tarefa[]>([]);
  const [undoStack, setUndoStack] = useState<UndoAction[]>([]);
  const [modalState, setModalState] = useState<HermesModalProps>({
    isOpen: false,
    title: '',
    message: '',
    type: 'alert',
    onConfirm: () => { }
  });
  const [googleCalendarEvents, setGoogleCalendarEvents] = useState<GoogleCalendarEvent[]>([]);
  const [entregas, setEntregas] = useState<EntregaInstitucional[]>([]);
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [isCompletedLogsOpen, setIsCompletedLogsOpen] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const handleCopyBacklog = async () => {
    const activeItems = workItems.filter(w => !w.concluido);
    if (activeItems.length === 0) {
      showToast("Nenhum item pendente para copiar.", "info");
      return;
    }

    const text = activeItems.map(item => {
      const systemName = unidades.find(u => u.id === item.sistema_id)?.nome.replace('SISTEMA:', '').trim() || 'Sistema Desconhecido';
      return `[${systemName}] ${item.descricao}`;
    }).join('\n');

    try {
      await navigator.clipboard.writeText(text);
      showToast("Backlog copiado para a área de transferência!", "success");
    } catch (err) {
      console.error('Failed to copy: ', err);
      showToast("Erro ao copiar.", "error");
    }
  };

  // Finance State
  const [financeTransactions, setFinanceTransactions] = useState<FinanceTransaction[]>([]);
  const [financeGoals, setFinanceGoals] = useState<FinanceGoal[]>([]);
  const [financeSettings, setFinanceSettings] = useState<FinanceSettings>({
    monthlyBudget: 5000,
    monthlyBudgets: {},
    sprintDates: { 1: "08", 2: "15", 3: "22", 4: "01" },
    emergencyReserveTarget: 0,
    emergencyReserveCurrent: 0,
    billCategories: ['Conta Fixa', 'Poupança', 'Investimento'],
    incomeCategories: ['Renda Principal', 'Renda Extra', 'Dividendos', 'Outros']
  });


  // Health State
  const [healthWeights, setHealthWeights] = useState<HealthWeight[]>([]);
  const [healthDailyHabits, setHealthDailyHabits] = useState<DailyHabits[]>([]);
  const [healthSettings, setHealthSettings] = useState<HealthSettings>({ targetWeight: 0 });

  // Systems State
  const [sistemasDetalhes, setSistemasDetalhes] = useState<Sistema[]>([]);
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [selectedSystemId, setSelectedSystemId] = useState<string | null>(null);
  const [selectedWorkItem, setSelectedWorkItem] = useState<WorkItem | null>(null);
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);
  const [isModalCompletedLogsOpen, setIsModalCompletedLogsOpen] = useState(false);
  const [isQuickLogModalOpen, setIsQuickLogModalOpen] = useState(false);
  const [isShoppingAIModalOpen, setIsShoppingAIModalOpen] = useState(false);
  const [isTranscriptionAIModalOpen, setIsTranscriptionAIModalOpen] = useState(false);
  const [editingResource, setEditingResource] = useState<{ field: string, label: string, value: string } | null>(null);

  const [newLogText, setNewLogText] = useState('');
  const [newLogTipo, setNewLogTipo] = useState<'desenvolvimento' | 'ajuste' | 'geral'>('geral');
  const [newLogAttachments, setNewLogAttachments] = useState<PoolItem[]>([]);
  const [editingWorkItem, setEditingWorkItem] = useState<WorkItem | null>(null);
  const [editingWorkItemText, setEditingWorkItemText] = useState('');
  const [editingWorkItemAttachments, setEditingWorkItemAttachments] = useState<PoolItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isRecordingLog, setIsRecordingLog] = useState(false);
  const [isProcessingLog, setIsProcessingLog] = useState(false);
  const logMediaRecorderRef = useRef<MediaRecorder | null>(null);
  const logAudioChunksRef = useRef<Blob[]>([]);

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isQuickNoteModalOpen, setIsQuickNoteModalOpen] = useState(false);
  const [hasAutoExpanded, setHasAutoExpanded] = useState(false);

  // Estados PGC
  const [atividadesPGC, setAtividadesPGC] = useState<AtividadeRealizada[]>([]);
  const [afastamentos, setAfastamentos] = useState<Afastamento[]>([]);
  const [pgcSubView, setPgcSubView] = useState<'audit' | 'heatmap' | 'config' | 'plano'>('audit');
  const [unidades, setUnidades] = useState<{ id: string, nome: string }[]>([]);
  const [sistemasAtivos, setSistemasAtivos] = useState<string[]>([]);

  // Knowledge State
  const [knowledgeItems, setKnowledgeItems] = useState<ConhecimentoItem[]>([]);
  // Shopping State
  const [shoppingItems, setShoppingItems] = useState<ShoppingItem[]>([]);
  // Projects State
  const [projects, setProjects] = useState<Projeto[]>([]);
  const [isProjectCreateModalOpen, setIsProjectCreateModalOpen] = useState(false);

  const [isImportPlanOpen, setIsImportPlanOpen] = useState(false);
  const [isCompletedTasksOpen, setIsCompletedTasksOpen] = useState(false);
  const [brainstormIdeas, setBrainstormIdeas] = useState<BrainstormIdea[]>([]);
  const [activeFerramenta, setActiveFerramenta] = useState<'brainstorming' | 'slides' | 'shopping' | 'transcription' | null>(null);
  const [isBrainstormingAddingText, setIsBrainstormingAddingText] = useState(false);
  const [confirmDeleteLogId, setConfirmDeleteLogId] = useState<string | null>(null);
  const [convertingIdea, setConvertingIdea] = useState<BrainstormIdea | null>(null);
  const [isSystemSelectorOpen, setIsSystemSelectorOpen] = useState(false);
  const [taskInitialData, setTaskInitialData] = useState<Partial<Tarefa> | null>(null);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser);
      setAuthLoading(false);
    });
    return () => unsubscribe();
  }, []);

  const handleLogin = async () => {
    try {
      await setPersistence(auth, rememberMe ? browserLocalPersistence : browserSessionPersistence);
      await signInWithPopup(auth, googleProvider);
      showToast("Login realizado com sucesso!", "success");
    } catch (error) {
      console.error("Erro ao fazer login:", error);
      showToast("Erro ao fazer login com Google.", "error");
    }
  };

  const handleLogout = async () => {
    try {
      await signOut(auth);
      showToast("Sessão encerrada.", "info");
    } catch (error) {
      console.error("Erro ao fazer logout:", error);
    }
  };

  const showAlert = (title: string, message: string, onConfirm?: () => void) => {
    setModalState({
      isOpen: true,
      title,
      message,
      type: 'alert',
      onConfirm: () => {
        setModalState(prev => ({ ...prev, isOpen: false }));
        if (onConfirm) onConfirm();
      }
    });
  };

  const showConfirm = (title: string, message: string, onConfirm: () => void, onCancel?: () => void) => {
    setModalState({
      isOpen: true,
      title,
      message,
      type: 'confirm',
      onConfirm: () => {
        setModalState(prev => ({ ...prev, isOpen: false }));
        onConfirm();
      },
      onCancel: () => {
        setModalState(prev => ({ ...prev, isOpen: false }));
        if (onCancel) onCancel();
      }
    });
  };

  const pushToUndoStack = (label: string, undo: () => Promise<void> | void) => {
    const action: UndoAction = {
      id: Math.random().toString(36).substr(2, 9),
      label,
      undo,
      timestamp: Date.now()
    };
    setUndoStack(prev => [action, ...prev].slice(0, 10));
  };

  const handleUndo = async () => {
    if (undoStack.length === 0) return;
    const [action, ...rest] = undoStack;
    await action.undo();
    setUndoStack(rest);
    showToast(`Desfeito: ${action.label}`, "info");
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        const target = e.target as HTMLElement;
        const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;
        if (!isInput) {
          e.preventDefault();
          handleUndo();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [undoStack]);

  const startLogRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      logMediaRecorderRef.current = mediaRecorder;
      logAudioChunksRef.current = [];
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) logAudioChunksRef.current.push(event.data);
      };
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(logAudioChunksRef.current, { type: 'audio/m4a' });
        await handleProcessLogAudio(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };
      mediaRecorder.start();
      setIsRecordingLog(true);
    } catch (err) {
      console.error("Erro ao acessar microfone:", err);
      showAlert("Erro", "Permissão de microfone negada ou não disponível.");
    }
  };

  const stopLogRecording = () => {
    if (logMediaRecorderRef.current && isRecordingLog) {
      logMediaRecorderRef.current.stop();
      setIsRecordingLog(false);
    }
  };

  const handleProcessLogAudio = async (audioBlob: Blob) => {
    setIsProcessingLog(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String });
          const data = response.data as { raw: string, refined: string };
          if (data.refined) {
            if (viewMode === 'sistemas-dev' && selectedSystemId) {
              await handleCreateWorkItem(selectedSystemId, newLogTipo, data.refined, newLogAttachments);
              setNewLogText('');
              setNewLogAttachments([]);
              showToast("Log registrado via IA!", "success");
            } else {
              setNewLogText(prev => prev ? prev + '\n' + data.refined : data.refined);
            }
          }
        } catch (error) {
          console.error("Erro ao transcrever:", error);
          showToast("Erro ao processar áudio via Hermes AI.", "error");
        } finally {
          setIsProcessingLog(false);
        }
      };
    } catch (error) {
      console.error("Erro ao ler áudio:", error);
      setIsProcessingLog(false);
    }
  };


  // Finance Sync
  useEffect(() => {
    const unsubSistemas = onSnapshot(collection(db, 'sistemas_detalhes'), (snapshot) => {
      setSistemasDetalhes(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as Sistema)));
    });

    const unsubGoogleCalendar = onSnapshot(collection(db, 'google_calendar_events'), (snapshot) => {
      setGoogleCalendarEvents(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as GoogleCalendarEvent)));
    });

    const unsubWorkItems = onSnapshot(collection(db, 'sistemas_work_items'), (snapshot) => {
      setWorkItems(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as WorkItem)));
    });

    const unsubTransactions = onSnapshot(collection(db, 'finance_transactions'), (snapshot) => {
      setFinanceTransactions(snapshot.docs
        .map(d => ({ id: d.id, ...d.data() } as FinanceTransaction))
        .filter(t => t.status !== 'deleted')
      );
    });
    const unsubGoals = onSnapshot(collection(db, 'finance_goals'), (snapshot) => {
      setFinanceGoals(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as FinanceGoal)));
    });
    const unsubSettings = onSnapshot(doc(db, 'finance_settings', 'config'), (doc) => {
      if (doc.exists()) {
        setFinanceSettings(doc.data() as FinanceSettings);
      }
    });

    const qFixedBills = query(collection(db, 'fixed_bills'));
    const unsubFixedBills = onSnapshot(qFixedBills, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as FixedBill));
      setFixedBills(data);
    });

    const unsubRubrics = onSnapshot(collection(db, 'bill_rubrics'), (snapshot) => {
      setBillRubrics(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as BillRubric)));
    });

    const unsubIncomeEntries = onSnapshot(collection(db, 'income_entries'), (snapshot) => {
      setIncomeEntries(snapshot.docs
        .map(d => ({ id: d.id, ...d.data() } as IncomeEntry))
        .filter(e => e.status !== 'deleted')
      );
    });

    const unsubIncomeRubrics = onSnapshot(collection(db, 'income_rubrics'), (snapshot) => {
      setIncomeRubrics(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as IncomeRubric)));
    });

    const unsubShopping = onSnapshot(collection(db, 'shopping_items'), (snapshot) => {
      setShoppingItems(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as ShoppingItem)));
    });

    // Projects Sync
    const qProjects = query(collection(db, 'projetos'), orderBy('data_criacao', 'desc')); // orderBy imported? Need to check imports
    const unsubProjects = onSnapshot(qProjects, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })) as Projeto[];
      setProjects(data);
    });

    // Health Sync
    const unsubHealthWeights = onSnapshot(collection(db, 'health_weights'), (snapshot) => {
      setHealthWeights(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as HealthWeight)));
    });
    const unsubHealthHabits = onSnapshot(collection(db, 'health_daily_habits'), (snapshot) => {
      setHealthDailyHabits(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as DailyHabits)));
    });
    const unsubHealthSettings = onSnapshot(doc(db, 'health_settings', 'config'), (doc) => {
      if (doc.exists()) setHealthSettings(doc.data() as HealthSettings);
    });
    const unsubscribeSistemasAtivos = onSnapshot(doc(db, 'configuracoes', 'sistemas'), (docSnap) => {
      if (docSnap.exists()) {
        setSistemasAtivos(docSnap.data().lista || []);
      }
    });

    return () => {
      unsubSistemas();
      unsubGoogleCalendar();
      unsubWorkItems();
      unsubTransactions();
      unsubGoals();
      unsubSettings();
      unsubFixedBills();
      unsubRubrics();
      unsubIncomeEntries();
      unsubIncomeRubrics();
      unsubShopping();
      unsubProjects();
      unsubHealthWeights();
      unsubHealthHabits();
      unsubHealthSettings();
      unsubscribeSistemasAtivos();
    };
  }, []);


  // Finance Processing Logic (The Listener)
  useEffect(() => {
    const processFinanceTasks = async () => {
      // Monitora TODAS as tarefas de Gasto Semanal (ativas ou concluídas) para garantir sincronia
      const financeTasks = tarefas.filter(t =>
        t.status !== 'excluído' as any &&
        t.titulo.toLowerCase().includes('gasto semanal') &&
        t.notas && /Tag:\s*GASTO\s*SEMANAL/i.test(t.notas)
      );

      for (const task of financeTasks) {
        const valueMatch = task.notas?.match(/Valor:\s*R\$\s*([\d\.,]+)/i);
        if (valueMatch) {
          try {
            // Normaliza valor (formato BR: 1.000,00 -> 1000.00)
            const amountStr = valueMatch[1].replace(/\./g, '').replace(',', '.');
            const amount = parseFloat(amountStr);

            if (isNaN(amount)) continue;

            // Recalcula dados (Data, Sprint)
            const dateMatch = task.titulo.match(/(\d{2}\/\d{2}\/\d{4})/);
            let transactionDate = new Date().toISOString();
            if (dateMatch) {
              const [d, m, y] = dateMatch[1].split('/').map(Number);
              transactionDate = new Date(y, m - 1, d).toISOString();
            }

            const day = new Date(transactionDate).getDate();
            // Lógica original de sprint: < 8, < 15, < 22, resto (4)
            const sprintOriginal = day < 8 ? 1 : day < 15 ? 2 : day < 22 ? 3 : 4;

            // Busca por ID original ou por período (título idêntico para Gasto Semanal)
            // Isso garante que se uma tarefa for apagada e recriada, ela atualize a transação existente em vez de duplicar
            const existingTransaction = financeTransactions.find(ft =>
              ft.originalTaskId === task.id ||
              (ft.category === 'Gasto Semanal' && ft.description.toLowerCase() === task.titulo.toLowerCase())
            );

            if (existingTransaction) {
              // UPDATE: Se já existe, verifica se houve mudança significativa
              const hasChanged = existingTransaction.amount !== amount ||
                existingTransaction.date !== transactionDate ||
                existingTransaction.originalTaskId !== task.id;

              if (hasChanged) {
                await updateDoc(doc(db, 'finance_transactions', existingTransaction.id), {
                  amount,
                  date: transactionDate,
                  sprint: sprintOriginal,
                  description: task.titulo,
                  originalTaskId: task.id // Atualiza o vínculo para a tarefa mais recente
                });

                if (existingTransaction.amount !== amount) {
                  showToast(`Valor atualizado: R$ ${amount.toLocaleString('pt-BR')}`, 'info');
                }
              }
            } else {
              // CREATE: Se não existe transação para este período/tarefa, cria uma nova
              await addDoc(collection(db, 'finance_transactions'), {
                description: task.titulo,
                amount,
                date: transactionDate,
                sprint: sprintOriginal,
                category: 'Gasto Semanal',
                originalTaskId: task.id
              });

              // Marca como concluída apenas se ainda não estiver
              if (normalizeStatus(task.status) !== 'concluido') {
                await updateDoc(doc(db, 'tarefas', task.id), {
                  status: 'concluído',
                  data_conclusao: formatDateLocalISO(new Date())
                });
                showToast(`Gasto processado: R$ ${amount.toLocaleString('pt-BR')}`, 'success');
              }
            }
          } catch (error) {
            console.error("Erro ao processar tarefa financeira:", error);
          }
        }
      }
    };

    if (tarefas.length > 0) {
      processFinanceTasks();
    }
  }, [tarefas, financeTransactions]); // Adicionado financeTransactions para garantir consistência

  // Auto-generate Fixed Bills from Rubrics
  useEffect(() => {
    if (billRubrics.length === 0) return;

    const missingBills: any[] = [];

    billRubrics.forEach(rubric => {
      const exists = fixedBills.some(b =>
        b.rubricId === rubric.id &&
        b.month === currentMonth &&
        b.year === currentYear
      );

      if (!exists) {
        missingBills.push({
          description: rubric.description,
          amount: rubric.defaultAmount || 0,
          dueDay: rubric.dueDay,
          month: currentMonth,
          year: currentYear,
          category: rubric.category,
          isPaid: false,
          rubricId: rubric.id
        });
      }
    });

    if (missingBills.length > 0) {
      const batch = writeBatch(db);
      missingBills.forEach(bill => {
        const ref = doc(collection(db, 'fixed_bills'));
        batch.set(ref, bill);
      });
      batch.commit().then(() => {
        showToast(`${missingBills.length} contas fixas geradas para este mês.`, 'info');
      }).catch(err => console.error("Erro ao gerar contas fixas:", err));
    }
  }, [billRubrics, fixedBills, currentMonth, currentYear]);


  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'success', action?: { label: string, onClick: () => void }, actions?: { label: string | React.ReactNode, onClick: () => void }[]) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts(prev => {
      // Evitar duplicatas exatas de mensagens ativas
      if (prev.some(t => t.message === message)) return prev;

      // Consolidar fluxo: se a nova mensagem for muito similar à última, substitui
      // Ex: "Enviando arquivo A...", "Enviando arquivo B..."
      if (prev.length > 0) {
        const last = prev[prev.length - 1];
        const lastPrefix = last.message.split(' ')[0];
        const newPrefix = message.split(' ')[0];
        if (lastPrefix === newPrefix && last.type === type && message.length > 10) {
          return [...prev.slice(0, -1), { id, message, type, action, actions }];
        }
      }

      // Limitar a no máximo 2 toasts simultâneos para não poluir a tela
      const base = prev.length >= 2 ? prev.slice(1) : prev;
      return [...base, { id, message, type, action, actions }];
    });

    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 5000);
  };

  const removeToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  const handleExportModule = () => {
    let md = '';
    let filename = 'hermes_export';

    if (viewMode === 'projects') {
       md = generateMarkdown(
         'Módulo de Projetos',
         'Listagem de todos os projetos cadastrados no sistema.',
         { 'Nome': 'Nome do projeto', 'Descrição': 'Resumo', 'Data': 'Data de criação' },
         [{ title: 'Projetos Ativos', data: projects.map(p => ({ Nome: p.nome, Descrição: p.descricao, Data: new Date(p.data_criacao).toLocaleDateString() })) }]
       );
       filename = 'hermes_projetos';
    } else if (viewMode === 'finance') {
       md = generateMarkdown(
         'Módulo Financeiro',
         'Transações, Metas e Obrigações.',
         { 'Data': 'Data da transação', 'Valor': 'Montante em BRL', 'Descrição': 'Detalhes' },
         [
           { title: 'Transações Recentes', data: financeTransactions.map(t => ({ Data: new Date(t.date).toLocaleDateString(), Descrição: t.description, Valor: t.amount })) },
           { title: 'Contas Fixas', data: fixedBills.filter(b => b.month === currentMonth && b.year === currentYear).map(b => ({ Descrição: b.description, Valor: b.amount, Status: b.isPaid ? 'Pago' : 'Pendente' })) }
         ]
       );
       filename = 'hermes_financeiro';
    } else if (viewMode === 'saude') {
       md = generateMarkdown(
         'Módulo de Saúde',
         'Registros de peso e hábitos.',
         { 'Data': 'Data do registro', 'Peso': 'Peso em kg' },
         [{ title: 'Histórico de Peso', data: healthWeights.map(w => ({ Data: new Date(w.date).toLocaleDateString(), Peso: w.weight })) }]
       );
       filename = 'hermes_saude';
    } else if (viewMode === 'gallery') {
       md = generateMarkdown(
         'Módulo de Ações',
         'Tarefas e atividades.',
         { 'Titulo': 'Nome da tarefa', 'Status': 'Estado atual' },
         [{ title: 'Tarefas', data: tarefas.map(t => ({ Titulo: t.titulo, Status: t.status, Prazo: t.data_limite })) }]
       );
       filename = 'hermes_acoes';
    } else if (viewMode === 'sistemas-dev') {
        const sys = selectedSystemId ? unidades.find(u => u.id === selectedSystemId)?.nome : 'Todos os Sistemas';
        md = generateMarkdown(
            `Módulo de Sistemas: ${sys}`,
            'Logs e itens de trabalho.',
            { 'Descrição': 'O que foi feito', 'Tipo': 'Classificação' },
            [{ title: 'Work Items', data: workItems.filter(w => !selectedSystemId || w.sistema_id === selectedSystemId).map(w => ({ Descrição: w.descricao, Tipo: w.tipo, Data: new Date(w.data_criacao).toLocaleDateString() })) }]
        );
        filename = 'hermes_sistemas';
    }

    if (md) downloadMarkdown(filename, md);
    else showToast('Exportação não disponível para esta visão.', 'info');
  };

  const handleCreateProject = async (name: string, desc: string) => {
    try {
      await addDoc(collection(db, 'projetos'), {
        nome: name,
        descricao: desc,
        data_criacao: new Date().toISOString()
      });
      setIsProjectCreateModalOpen(false);
      showToast("Projeto criado com sucesso!", "success");
    } catch (error) {
      console.error("Error creating project:", error);
      showToast("Erro ao criar projeto.", "error");
    }
  };

  const handleBatchTag = async (categoria: Categoria) => {
    if (selectedTaskIds.length === 0) return;
    try {
      setLoading(true);
      const batchSize = selectedTaskIds.length;

      const promises = selectedTaskIds.map(async (id) => {
        const t = tarefas.find(task => task.id === id);
        if (!t) return;

        let finalNotes = t.notas || '';
        const tagStr = `Tag: ${categoria}`;
        finalNotes = finalNotes.replace(/Tag:\s*(CLC|ASSISTÊNCIA|GERAL|NÃO CLASSIFICADA)/gi, '').trim();
        finalNotes = finalNotes ? `${finalNotes}\n\n${tagStr}` : tagStr;

        return updateDoc(doc(db, 'tarefas', id), {
          categoria: categoria,
          notas: finalNotes,
          data_atualizacao: new Date().toISOString()
        });
      });

      await Promise.all(promises);
      setSelectedTaskIds([]);
      showToast(`${batchSize} tarefas atualizadas!`, 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar em lote.", 'error');
    } finally {
      setLoading(false);
    }
  };

  // Dashboard states
  const [dashboardViewMode, setDashboardViewMode] = useState<'list' | 'calendar'>('list');
  const [fixedBills, setFixedBills] = useState<FixedBill[]>([]);
  const [billRubrics, setBillRubrics] = useState<BillRubric[]>([]);
  const [incomeEntries, setIncomeEntries] = useState<IncomeEntry[]>([]);
  const [incomeRubrics, setIncomeRubrics] = useState<IncomeRubric[]>([]);
  const [calendarViewMode, setCalendarViewMode] = useState<'month' | 'week' | 'day'>('month');
  const [calendarDate, setCalendarDate] = useState(new Date());

  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeModule, setActiveModule] = useState<'home' | 'dashboard' | 'acoes' | 'financeiro' | 'saude' | 'projetos'>('dashboard');
  const [viewMode, setViewMode] = useState<'dashboard' | 'gallery' | 'pgc' | 'licitacoes' | 'assistencia' | 'sistemas' | 'finance' | 'saude' | 'ferramentas' | 'sistemas-dev' | 'knowledge' | 'projects'>('dashboard');
  const [selectedTask, setSelectedTask] = useState<Tarefa | null>(null);
  const [isSidebarRetracted, setIsSidebarRetracted] = useState(false);
  const [financeActiveTab, setFinanceActiveTab] = useState<'dashboard' | 'fixed'>('dashboard');
  const [isFinanceSettingsOpen, setIsFinanceSettingsOpen] = useState(false);

  // Modal Mode State
  const [taskModalMode, setTaskModalMode] = useState<'default' | 'edit' | 'execute'>('default');

  // Reset modal mode when selected task is cleared
  useEffect(() => {
    if (!selectedTask) {
      setTaskModalMode('default');
    }
  }, [selectedTask]);

  // Sync selectedTask with updated data from Firestore to ensure components have latest data
  useEffect(() => {
    if (selectedTask) {
      const updated = tarefas.find(t => t.id === selectedTask.id);
      if (updated && JSON.stringify(updated) !== JSON.stringify(selectedTask)) {
        setSelectedTask(updated);
      }
    }
  }, [tarefas, selectedTask]);
  const [planosTrabalho, setPlanosTrabalho] = useState<PlanoTrabalho[]>([]);
  const [statusFilter, setStatusFilter] = useState<Status[]>(['em andamento']);
  const [areaFilter, setAreaFilter] = useState<string>('TODAS');
  const [sortOption, setSortOption] = useState<SortOption>('date-asc');
  const [expandedSections, setExpandedSections] = useState<string[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [notifications, setNotifications] = useState<HermesNotification[]>([]);
  const [isNotificationCenterOpen, setIsNotificationCenterOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [syncData, setSyncData] = useState<any>(null);
  const [activePopup, setActivePopup] = useState<HermesNotification | null>(null);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [exams, setExams] = useState<HealthExam[]>([]);
  const [lastBackPress, setLastBackPress] = useState(0);

  const handleDashboardNavigate = (view: 'gallery' | 'finance' | 'saude' | 'sistemas-dev') => {
    setViewMode(view);
    if (view === 'gallery' || view === 'sistemas-dev') setActiveModule('acoes');
    else if (view === 'finance') setActiveModule('financeiro');
    else if (view === 'saude') setActiveModule('saude');
  };

  // Sync state changes with history to enable back button
  useEffect(() => {
    // Only push if we are NOT at dashboard (root)
    if (activeModule !== 'dashboard' || viewMode !== 'dashboard' || selectedSystemId || isLogsModalOpen || activeFerramenta) {
      window.history.pushState({ activeModule, viewMode, selectedSystemId, isLogsModalOpen, activeFerramenta }, "", window.location.pathname);
    }
  }, [activeModule, viewMode, selectedSystemId, isLogsModalOpen, activeFerramenta]);

  // Handle hardware/browser back button
  useEffect(() => {
    const handlePopState = (e: PopStateEvent) => {
      if (isLogsModalOpen) {
        setIsLogsModalOpen(false);
        e.preventDefault();
      } else if (selectedSystemId) {
        setSelectedSystemId(null);
        e.preventDefault();
      } else if (activeFerramenta) {
        setActiveFerramenta(null);
        e.preventDefault();
      } else if (viewMode !== 'dashboard') {
        setActiveModule('dashboard');
        setViewMode('dashboard');
        e.preventDefault();
      } else {
        const now = Date.now();
        if (now - lastBackPress < 2000) return;
        e.preventDefault();
        setLastBackPress(now);
        showToast("Pressione voltar novamente para minimizar", "info");
        // Maintain the history entry to wait for second press
        window.history.pushState(null, "", window.location.pathname);
      }
    };

    // Initial dummy state to capture back press
    if (window.history.state === null) {
      window.history.pushState({}, "", window.location.pathname);
    }

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [activeModule, viewMode, selectedSystemId, isLogsModalOpen, activeFerramenta, lastBackPress]);
  const [appSettings, setAppSettings] = useState<AppSettings>(DEFAULT_APP_SETTINGS);
  const [isHabitsReminderOpen, setIsHabitsReminderOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<'notifications' | 'context' | 'sistemas'>('notifications');

  // --- HermesNotification System & App Settings ---

  // --- Firebase Cloud Messaging (FCM) & Push Notifications ---
  useEffect(() => {
    const setupFCM = async () => {
      if (!messaging) return;
      try {
        console.log('Iniciando configuração de Push...');
        const permission = await Notification.requestPermission();
        console.log('Permissão de Notificação:', permission);

        if (permission === 'granted') {
          // Garante que o service worker está registrado antes de pedir o token
          const registration = await navigator.serviceWorker.ready;

          const token = await getToken(messaging, {
            vapidKey: 'BBXF5bMrAdRIXKGLHXMzsZSREaQoVo2VbVgcJJkA7_qu05v2GOcCqgLRjc54airIqf087t46jvggg7ZdmPzuqiE',
            serviceWorkerRegistration: registration
          }).catch(err => {
            console.error("Erro ao obter FCM Token:", err);
            return null;
          });

          if (token) {
            console.log('FCM Token obtido com sucesso:', token);
            await setDoc(doc(db, 'fcm_tokens', token), {
              token,
              last_updated: new Date().toISOString(),
              platform: 'web_pwa',
              userAgent: navigator.userAgent
            });
            console.log('Token persistido no Firestore.');
          } else {
            console.warn('FCM Token não foi gerado. Verifique a VAPID Key no Firebase Console.');
          }
        }
      } catch (error) {
        console.error('Falha crítica no setup do FCM:', error);
      }
    };

    setupFCM();

    const unsubscribe = onMessage(messaging!, (payload) => {
      console.log('Mensagem PUSH recebida em primeiro plano:', payload);
      if (payload.notification) {
        const newNotif: HermesNotification = {
          id: Math.random().toString(36).substr(2, 9),
          title: payload.notification.title || 'Hermes',
          message: payload.notification.body || '',
          type: 'info',
          timestamp: new Date().toISOString(),
          isRead: false,
          link: (payload.data as any)?.link || ""
        };
        setNotifications(prev => [newNotif, ...prev]);
        setActivePopup(newNotif);
      }
    });

    return () => unsubscribe();
  }, []);

  const emitNotification = async (title: string, message: string, type: 'info' | 'warning' | 'success' | 'error' = 'info', link?: string, id?: string) => {
    const newNotif: HermesNotification = {
      id: id || Math.random().toString(36).substr(2, 9),
      title,
      message,
      type,
      timestamp: new Date().toISOString(),
      isRead: false,
      link: link || ""
    };

    // 1. Atualiza estado local para feedback imediato (evita duplicados por ID)
    setNotifications(prev => {
      if (prev.some(n => n.id === newNotif.id)) return prev;
      return [newNotif, ...prev];
    });
    setActivePopup(newNotif);

    // 2. Persiste no Firestore para disparar Push Notification via Cloud Function
    try {
      // Usa setDoc com ID específico para evitar duplicados no Firestore
      // Garante que não há campos undefined
      const firestoreData = JSON.parse(JSON.stringify(newNotif));

      // Verifica configurações globais de push
      const shouldSendPush = appSettings.notifications?.enablePush !== false; // Default true

      await setDoc(doc(db, 'notificacoes', newNotif.id), {
        ...firestoreData,
        sent_to_push: !shouldSendPush // Se não deve enviar, já marca como enviado para a function ignorar
      });
    } catch (err) {
      console.error("Erro ao persistir notificação:", err);
      // Feedback visual do erro para o usuário (agora que estamos validando)
      showToast(`Erro no sistema de notificação: ${err}`, "error");
    }
  };

  useEffect(() => {
    const unsub = onSnapshot(doc(db, 'configuracoes', 'geral'), (snap) => {
      if (snap.exists()) {
        setAppSettings(snap.data() as AppSettings);
      }
    });
    return () => unsub();
  }, []);

  const handleUpdateAppSettings = async (newSettings: AppSettings) => {
    try {
      await setDoc(doc(db, 'configuracoes', 'geral'), newSettings);
      showToast("Configurações atualizadas!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao salvar configurações.", "error");
    }
  };

  const handleUpdateOverdueTasks = async (notificationId?: string) => {
    const todayStr = formatDateLocalISO(new Date());
    const overdue = tarefas.filter(t =>
      normalizeStatus(t.status) !== 'concluido' &&
      t.status !== 'excluído' as any &&
      t.data_limite && t.data_limite !== "-" && t.data_limite !== "0000-00-00" &&
      t.data_limite < todayStr
    );

    if (overdue.length === 0) {
      showToast("Nenhuma ação atrasada encontrada.", 'info');
      if (notificationId) handleDismissNotification(notificationId);
      return;
    }

    try {
      const batch = writeBatch(db);

      overdue.forEach(t => {
        batch.update(doc(db, 'tarefas', t.id), {
          data_limite: todayStr,
          horario_inicio: null,
          horario_fim: null,
          data_atualizacao: new Date().toISOString()
        });
      });

      await batch.commit();
      showToast(`${overdue.length} ações atualizadas para hoje!`, 'success');

      if (notificationId) {
        handleDismissNotification(notificationId);
      } else {
        const targetNotif = notifications.find(n => n.title === "Ações Vencidas");
        if (targetNotif) handleDismissNotification(targetNotif.id);
      }
    } catch (err) {
      console.error("Erro ao atualizar tarefas:", err);
      showToast("Erro ao atualizar tarefas.", 'error');
    }
  };

  const handleUpdateToToday = async (task: Tarefa) => {
    const todayStr = formatDateLocalISO(new Date());
    try {
      await updateDoc(doc(db, 'tarefas', task.id), {
        data_limite: todayStr,
        horario_inicio: null,
        horario_fim: null,
        data_atualizacao: new Date().toISOString()
      });
      showToast("Ação atualizada para hoje!", 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar ação.", 'error');
    }
  };

  const handleNotificationNavigate = (link: string) => {
    if (!link) return;

    switch (link) {
      case 'acoes':
        setActiveModule('acoes');
        setViewMode('gallery');
        break;
      case 'financeiro':
        setActiveModule('financeiro');
        setViewMode('finance');
        break;
      case 'pgc':
        setActiveModule('acoes');
        setViewMode('pgc');
        break;
      case 'saude':
        setActiveModule('saude');
        setViewMode('saude');
        break;
      case 'sistemas':
        setActiveModule('acoes');
        setViewMode('sistemas-dev');
        break;
      default:
        break;
    }
  };

  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  // HermesNotification System Triggers (Time-based: Habits, Weigh-in)
  useEffect(() => {
    const interval = setInterval(() => {
      const now = new Date();
      const current_time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

      // Calculate local date string (YYYY-MM-DD) to match local time configuration
      const todayStr = formatDateLocalISO(now);

      // 1. Habits Reminder
      if (appSettings.notifications.habitsReminder.enabled && current_time === appSettings.notifications.habitsReminder.time) {
        const lastOpen = localStorage.getItem('lastHabitsReminderDate');
        if (lastOpen !== todayStr) {
          setIsHabitsReminderOpen(true);
          localStorage.setItem('lastHabitsReminderDate', todayStr);
        }
      }

      // 2. Weigh-in Reminder (Bell HermesNotification)
      if (appSettings.notifications.weighInReminder.enabled && current_time === appSettings.notifications.weighInReminder.time) {
        const lastWeighInRemind = localStorage.getItem('lastWeighInRemindDate');
        if (lastWeighInRemind !== todayStr) {
          const dayMatch = now.getDay() === appSettings.notifications.weighInReminder.dayOfWeek;
          let shouldRemind = false;

          if (appSettings.notifications.weighInReminder.frequency === 'weekly' && dayMatch) {
            shouldRemind = true;
          } else if (appSettings.notifications.weighInReminder.frequency === 'biweekly') {
            const weekRef = Math.floor(now.getTime() / (7 * 24 * 60 * 60 * 1000));
            if (dayMatch && weekRef % 2 === 0) shouldRemind = true;
          } else if (appSettings.notifications.weighInReminder.frequency === 'monthly' && now.getDate() === 1) {
            shouldRemind = true;
          }

          if (shouldRemind) {
            emitNotification(
              "Lembrete de Pesagem",
              "Hora de registrar seu peso para acompanhar sua evolução no módulo Saúde!",
              'info',
              'saude',
              `weigh_in_${todayStr}`
            );
            localStorage.setItem('lastWeighInRemindDate', todayStr);
          }
        }
      }
      // 3. Daily Task Notifications
      const currentTimeInMinutes = now.getHours() * 60 + now.getMinutes();
      tarefas.forEach(t => {
        if (t.status === 'concluído' || t.data_limite !== todayStr) return;

        if (t.horario_inicio) {
          const [h, m] = t.horario_inicio.split(':').map(Number);
          const startMin = h * 60 + m;
          const diff = startMin - currentTimeInMinutes;
          const lastReminded = localStorage.getItem(`lastStartRemind_${t.id}`);
          if (diff === 15 && lastReminded !== todayStr) {
            const msg = `Sua tarefa "${t.titulo}" inicia em 15 minutos!`;
            emitNotification("Hermes: Próxima Tarefa", msg, 'info', '', `task_start_${t.id}_${todayStr}`);
            localStorage.setItem(`lastStartRemind_${t.id}`, todayStr);
          }
        }

        if (t.horario_fim) {
          const [h, m] = t.horario_fim.split(':').map(Number);
          const endMin = h * 60 + m;
          const diff = endMin - currentTimeInMinutes;
          const lastReminded = localStorage.getItem(`lastEndRemind_${t.id}`);
          if (diff === 15 && lastReminded !== todayStr) {
            const msg = `Sua tarefa "${t.titulo}" encerra em 15 minutos!`;
            emitNotification("Hermes: Encerramento de Tarefa", msg, 'info', '', `task_end_${t.id}_${todayStr}`);
            localStorage.setItem(`lastEndRemind_${t.id}`, todayStr);
          }
        }
      });

      // 4. Custom Notifications
      const customNotifs = appSettings.notifications.custom || [];
      customNotifs.forEach((notif: CustomNotification) => {
        if (!notif.enabled) return;
        if (notif.time === current_time) {
          const NOTIF_KEY = `lastCustomNotif_${notif.id}`;
          const lastSent = localStorage.getItem(NOTIF_KEY);

          if (lastSent === todayStr) return;

          let shouldSend = false;
          if (notif.frequency === 'daily') {
            shouldSend = true;
          } else if (notif.frequency === 'weekly') {
            const dayOfWeek = now.getDay(); // 0-6
            if (notif.daysOfWeek && notif.daysOfWeek.includes(dayOfWeek)) {
              shouldSend = true;
            }
          } else if (notif.frequency === 'monthly') {
            const dayOfMonth = now.getDate();
            if (dayOfMonth === notif.dayOfMonth) {
              shouldSend = true;
            }
          }

          if (shouldSend) {
            emitNotification("Lembrete Personalizado", notif.message, 'info', '', `custom_${notif.id}_${todayStr}`);
            localStorage.setItem(NOTIF_KEY, todayStr);
          }
        }
      });

    }, 10000); // Check every 10 seconds to ensure we don't miss the minute
    return () => clearInterval(interval);
  }, [appSettings.notifications, tarefas]);

  // Data-driven Notifications (Budget, Overdue, PGC)
  useEffect(() => {
    const todayStr = formatDateLocalISO(new Date());

    // 1. Overdue Tasks (Once a day check)
    if (appSettings.notifications.overdueTasks.enabled && localStorage.getItem('lastOverdueCheckDate') !== todayStr) {
      const overdueCount = tarefas.filter(t =>
        normalizeStatus(t.status) !== 'concluido' &&
        t.status !== 'excluído' as any &&
        t.data_limite && t.data_limite !== "-" && t.data_limite !== "0000-00-00" &&
        t.data_limite < todayStr
      ).length;

      if (overdueCount > 0) {
        emitNotification(
          "Ações Vencidas",
          `Você tem ${overdueCount} ações fora do prazo. Que tal atualizá-las para hoje?`,
          'warning',
          'acoes',
          `overdue-${todayStr}`
        );
        localStorage.setItem('lastOverdueCheckDate', todayStr);
      }
    }

    // 2. Budget Risk (Whenever data changes, throttled to once per day notification AND real spending increase)
    if (appSettings.notifications.budgetRisk.enabled) {
      const now = new Date();
      const currentMonthStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
      const monthlyBudget = financeSettings.monthlyBudgets?.[currentMonthStr] || financeSettings.monthlyBudget;
      const totalSpend = financeTransactions.filter(t => {
        const d = new Date(t.date);
        return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
      }).reduce((acc, t) => acc + t.amount, 0);

      if (monthlyBudget > 0) {
        const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
        const currentDay = now.getDate();
        const budgetRatio = totalSpend / monthlyBudget;
        const timeRatio = currentDay / daysInMonth;

        // Condition: Over budget velocity AND (New day OR spending increased since last notification)
        const lastNotifiedSpend = parseFloat(localStorage.getItem(`lastBudgetRiskNotifiedSpend_${currentMonthStr}`) || '0');
        const isNewDay = localStorage.getItem('lastBudgetRiskNotifyDate') !== todayStr;
        const hasSpendIncreased = totalSpend > lastNotifiedSpend;

        if (budgetRatio > timeRatio * 1.15 && budgetRatio > 0.1 && hasSpendIncreased && isNewDay) {
          emitNotification(
            "Alerta de Orçamento",
            `Atenção: Gastos elevados! Você já utilizou ${(budgetRatio * 100).toFixed(0)}% do orçamento em ${(timeRatio * 100).toFixed(0)}% do mês.`,
            'warning',
            'financeiro',
            `budget-${todayStr}`
          );
          localStorage.setItem('lastBudgetRiskNotifyDate', todayStr);
          localStorage.setItem(`lastBudgetRiskNotifiedSpend_${currentMonthStr}`, totalSpend.toString());
        }
      }
    }

    // 3. Audit PGC
    if (appSettings.notifications.pgcAudit.enabled && localStorage.getItem('lastPgcNotifyDate') !== todayStr) {
      const now = new Date();
      const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
      if ((daysInMonth - now.getDate()) <= appSettings.notifications.pgcAudit.daysBeforeEnd) {
        emitNotification(
          "Auditoria PGC",
          "O mês está acabando. Verifique no módulo PGC se todas as entregas possuem ações vinculadas.",
          'info',
          'pgc',
          `pgc-${todayStr}`
        );
        localStorage.setItem('lastPgcNotifyDate', todayStr);
      }
    }
  }, [tarefas, financeTransactions, financeSettings, planosTrabalho, appSettings.notifications]);

  // Welcome HermesNotification
  useEffect(() => {
    const hasSeenWelcome = localStorage.getItem('hasSeenWelcome');
    if (!hasSeenWelcome && notifications.length === 0) {
      emitNotification(
        'Bem-vindo ao Hermes',
        'Sistema de notificações ativo. Configure suas preferências no ícone de engrenagem.',
        'info',
        undefined,
        'welcome'
      );
      localStorage.setItem('hasSeenWelcome', 'true');
    }
  }, []);

  // Sync Logic
  useEffect(() => {
    const unsub = onSnapshot(doc(db, 'system', 'sync'), (snap) => {
      if (snap.exists()) {
        const data = snap.data();
        setSyncData(data);
        if (data.status === 'processing' || data.status === 'requested') setIsSyncing(true);
        if (data.status === 'completed' || data.status === 'error') setIsSyncing(false);
      }
    });
    return () => unsub();
  }, []);

  const handleSync = async () => {
    if (isSyncing) {
      setIsTerminalOpen(true);
      return;
    }

    setIsTerminalOpen(true);
    setIsSyncing(true);
    showToast("Iniciando Sincronização Profunda...", "info");

    try {
      await setDoc(doc(db, 'system', 'sync'), {
        status: 'requested',
        timestamp: new Date().toISOString(),
        logs: ["Aguardando resposta do Bot..."]
      });
    } catch (e) {
      console.error(e);
      showToast("Erro ao solicitar sincronização.", "error");
      setIsSyncing(false);
    }
  };


  const handleUpdateTarefa = async (id: string, updates: Partial<Tarefa>, suppressToast = false) => {
    try {
      const docRef = doc(db, 'tarefas', id);
      await updateDoc(docRef, {
        ...updates,
        data_atualizacao: new Date().toISOString()
      });

      // Mirror to Knowledge base
      if (updates.pool_dados && updates.pool_dados.length > 0) {
        for (const item of updates.pool_dados) {
          const knowledgeItem: ConhecimentoItem = {
            id: item.id,
            titulo: item.nome || 'Sem título',
            tipo_arquivo: item.tipo === 'link' ? 'link' : (item.nome?.split('.').pop()?.toLowerCase() || 'unknown'),
            url_drive: item.valor,
            tamanho: 0,
            data_criacao: item.data_criacao,
            origem: { modulo: 'tarefas', id_origem: id },
            categoria: 'Ações'
          };
          setDoc(doc(db, 'conhecimento', item.id), knowledgeItem).catch(console.error);
        }
      }

      if (!suppressToast) showToast("Tarefa atualizada!", 'success');
    } catch (err) {
      console.error("Erro ao atualizar tarefa:", err);
      showToast("Erro ao salvar alterações.", 'error');
    }
  };

  const handleReorderTasks = async (taskId: string, targetTaskId: string, label?: string) => {
    let currentLabel = label;
    if (!currentLabel) {
      // Encontra em qual bucket o target está
      for (const [l, ts] of Object.entries(tarefasAgrupadas)) {
        if (ts.some(t => t.id === targetTaskId)) {
          currentLabel = l;
          break;
        }
      }
    }
    if (!currentLabel) return;

    const tasksInBucket = [...(tarefasAgrupadas[currentLabel] || [])];
    if (tasksInBucket.length === 0) return;

    const oldIndex = tasksInBucket.findIndex(t => t.id === taskId);
    const newIndex = tasksInBucket.findIndex(t => t.id === targetTaskId);

    // Se estiver movendo dentro do mesmo bucket
    if (oldIndex !== -1) {
      if (oldIndex === newIndex) return;
      const [removed] = tasksInBucket.splice(oldIndex, 1);
      tasksInBucket.splice(newIndex, 0, removed);
    } else {
      // Movendo de outro bucket para este
      const draggedTask = tarefas.find(t => t.id === taskId);
      if (!draggedTask) return;
      const targetTask = tasksInBucket[newIndex];

      // Atualiza a data da tarefa arrastada para coincidir com o bucket de destino
      const newDate = targetTask.data_limite || formatDateLocalISO(new Date());
      await updateDoc(doc(db, 'tarefas', taskId), {
        data_limite: newDate,
        data_inicio: draggedTask.horario_inicio ? newDate : (draggedTask.data_inicio || newDate),
        data_atualizacao: new Date().toISOString()
      });

      // Insere na posição correta para o remapeamento de ordem
      tasksInBucket.splice(newIndex, 0, { ...draggedTask, data_limite: newDate });
    }

    // Reatribui ordens
    const promises = tasksInBucket.map((t, i) => {
      if (t.ordem !== i) {
        return updateDoc(doc(db, 'tarefas', t.id), { ordem: i, data_atualizacao: new Date().toISOString() });
      }
      return null;
    }).filter(Boolean);

    if (promises.length > 0) {
      await Promise.all(promises);
      showToast("Ordem atualizada!", "success");
    }
  };

  const handleToggleTarefaStatus = async (id: string, currentStatus: string) => {
    const tarefa = tarefas.find(t => t.id === id);
    if (!tarefa) return;
    const oldStatus = tarefa.status;
    const oldDataConclusao = tarefa.data_conclusao || null;

    try {
      const isConcluido = normalizeStatus(currentStatus) === 'concluido';
      const newStatus = isConcluido ? 'em andamento' : 'concluído';
      const now = new Date().toISOString();

      await updateDoc(doc(db, 'tarefas', id), {
        status: newStatus,
        data_conclusao: !isConcluido ? now : null,
        data_atualizacao: now
      });

      pushToUndoStack(isConcluido ? "Alterar Status" : "Concluir Tarefa", async () => {
        await updateDoc(doc(db, 'tarefas', id), {
          status: oldStatus,
          data_conclusao: oldDataConclusao,
          data_atualizacao: new Date().toISOString()
        });
      });

      showToast(isConcluido ? "Tarefa reaberta!" : "Tarefa concluída!", 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao alterar status.", 'error');
    }
  };

  const handleDeleteTarefa = async (id: string) => {
    const tarefa = tarefas.find(t => t.id === id);
    if (!tarefa) return;

    try {
      setLoading(true);
      const docRef = doc(db, 'tarefas', id);
      // Marcamos como excluída para o push-tasks remover do Google
      await updateDoc(docRef, {
        status: 'excluído' as any,
        data_atualizacao: new Date().toISOString()
      });

      pushToUndoStack("Excluir Tarefa", async () => {
        await updateDoc(docRef, {
          status: tarefa.status,
          data_atualizacao: new Date().toISOString()
        });
      });

      showToast('Tarefa excluída!', 'success');
    } catch (err) {
      console.error("Erro ao excluir tarefa:", err);
      showToast("Erro ao excluir.", 'error');
    } finally {
      setLoading(false);
    }
  };


  const handleUpdateIdea = async (id: string, text: string) => {
    try {
      await updateDoc(doc(db, 'brainstorm_ideas', id), { text });
      showToast("Nota atualizada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar nota.", "error");
    }
  };

  const handleDeleteKnowledgeItem = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'conhecimento', id));
      showToast("Arquivo removido do repositório.", "info");
    } catch (e) {
      showToast("Erro ao remover arquivo.", "error");
    }
  };

  const handleUploadKnowledgeFile = async (file: File) => {
    const item = await handleFileUploadToDrive(file);
    if (item) {
      const knowledgeItem: ConhecimentoItem = {
        id: item.id,
        titulo: item.nome || 'Sem título',
        tipo_arquivo: (file.name.includes('.') ? file.name.split('.').pop()?.toLowerCase() : 'unknown') || 'unknown',
        url_drive: item.valor,
        tamanho: 0,
        data_criacao: item.data_criacao,
        origem: null // Upload direto
      };
      await setDoc(doc(db, 'conhecimento', item.id), knowledgeItem);
      showToast("Arquivo enviado e indexação iniciada.", "success");
    }
  };

  const handleProcessarIA = async (itemId: string) => {
    try {
      const processarIA = httpsCallable(functions, 'processarArquivoIA');
      // No front-end limpamos os campos para dar feedback visual imediato se quisermos, 
      // mas o backend já faz isso. O importante é o feedback de "Solicitando..."
      showToast("Solicitando processamento à IA...", "info");

      const result = await processarIA({ itemId });
      const data = result.data as any;

      if (data.success) {
        showToast("Arquivo processado com sucesso!", "success");
      } else {
        showToast("Erro ao processar: " + (data.error || "Erro desconhecido"), "error");
      }
    } catch (err) {
      console.error(err);
      showToast("Falha na comunicação com a IA.", "error");
    }
  };

  const handleNavigateToOrigin = (modulo: string, id: string) => {
    switch (modulo) {
      case 'tarefas':
        const task = tarefas.find(t => t.id === id);
        if (task) {
          setSelectedTask(task);
          if (task.categoria === 'CLC') setViewMode('licitacoes');
          else if (task.categoria === 'ASSISTÊNCIA') setViewMode('assistencia');
          else setViewMode('gallery');
          setActiveModule('acoes');
        } else {
          showToast("Ação não encontrada.", "error");
        }
        break;
      case 'sistemas':
        const workItem = workItems.find(w => w.id === id);
        if (workItem) {
          setSelectedSystemId(workItem.sistema_id);
          setViewMode('sistemas-dev');
          setActiveModule('acoes');
          // setIsLogsModalOpen(true); // Opcional: abrir modal se existir
        } else {
          showToast("Log de sistema não encontrado.", "error");
        }
        break;
      case 'saude':
        const exam = exams.find(e => e.id === id);
        if (exam) {
          setViewMode('saude');
          setActiveModule('saude');
        } else {
          showToast("Exame não encontrado.", "error");
        }
        break;
      default:
        showToast("Módulo não mapeado para navegação.", "info");
    }
  };

  const handleFinalizeIdeaConversion = async (sistemaId: string) => {
    if (!convertingIdea) return;
    const unit = unidades.find(u => u.id === sistemaId);
    if (!unit) return;

    // Criar o log no sistema ao invés de uma tarefa geral (ação)
    await handleCreateWorkItem(sistemaId, 'ajuste', convertingIdea.text, [], true);

    // Remover a nota original após a conversão bem-sucedida
    await deleteDoc(doc(db, 'brainstorm_ideas', convertingIdea.id));

    setIsSystemSelectorOpen(false);
    setConvertingIdea(null);
    showToast("Nota convertida em log do sistema com sucesso!", "success");
  };

  const handleConvertToTask = (idea: BrainstormIdea) => {
    const timeMatch = idea.text.match(/\[Horário:\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\]/);
    const start = timeMatch ? timeMatch[1] : '';
    const end = timeMatch ? timeMatch[2] : '';

    setTaskInitialData({
      titulo: idea.text.replace(/\[Horário:\s*\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\]/g, '').trim(),
      notas: idea.text,
      horario_inicio: start,
      horario_fim: end,
      data_inicio: formatDateLocalISO(new Date()),
      data_limite: formatDateLocalISO(new Date())
    });
    setConvertingIdea(idea); // To delete after save
    setIsCreateModalOpen(true);
  };

  const handleUpdateSistema = async (id: string, updates: Partial<Sistema>) => {
    try {
      // Check if document exists first or use setDoc with merge
      await setDoc(doc(db, 'sistemas_detalhes', id), {
        ...updates,
        data_atualizacao: new Date().toISOString()
      }, { merge: true });
      showToast("Sistema atualizado!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar sistema.", "error");
    }
  };

  const handleCreateWorkItem = async (sistemaId: string, tipo: 'desenvolvimento' | 'ajuste' | 'log' | 'geral', descricao: string, attachments: PoolItem[] = [], suppressToast = false) => {
    const finalTipo = tipo === 'geral' ? 'ajuste' : tipo;
    try {
      if (!descricao.trim()) return;
      const docRef = await addDoc(collection(db, 'sistemas_work_items'), {
        sistema_id: sistemaId,
        tipo: finalTipo,
        descricao,
        concluido: false,
        data_criacao: new Date().toISOString(),
        pool_dados: attachments
      });

      // Mirror to Knowledge base
      if (attachments.length > 0) {
        for (const item of attachments) {
          const knowledgeItem: ConhecimentoItem = {
            id: item.id,
            titulo: item.nome || 'Sem título',
            tipo_arquivo: item.tipo === 'link' ? 'link' : (item.nome?.split('.').pop()?.toLowerCase() || 'unknown'),
            url_drive: item.valor,
            tamanho: 0,
            data_criacao: item.data_criacao,
            origem: { modulo: 'sistemas', id_origem: docRef.id }
          };
          setDoc(doc(db, 'conhecimento', item.id), knowledgeItem).catch(console.error);
        }
      }

      if (!suppressToast) {
        showToast(`${tipo === 'desenvolvimento' ? 'Desenvolvimento' : 'Ajuste'} registrado!`, "success");
      }
    } catch (err) {
      console.error(err);
      showToast("Erro ao criar item.", "error");
    }
  };

  const handleShoppingAIConfirm = async (confirmedItems: { id: string; quantidade: string }[]) => {
    try {
      const batch = writeBatch(db);
      let count = 0;
      confirmedItems.forEach(c => {
        const exists = shoppingItems.find(i => i.id === c.id);
        if (exists) {
          batch.update(doc(db, 'shopping_items', c.id), { isPlanned: true, quantidade: c.quantidade, isPurchased: false });
          count++;
        }
      });

      if (count > 0) {
        await batch.commit();
        showToast(`${count} iten${count !== 1 ? 's' : ''} adicionado${count !== 1 ? 's' : ''} ao planejamento!`, 'success', { label: 'Ver Lista', onClick: () => setActiveFerramenta('shopping') });
      } else {
        showToast('Nenhum item atualizado.', 'info');
      }
    } catch (err) {
      console.error(err);
      showToast('Erro ao atualizar planejamento.', 'error');
    }
  };


  const handleUpdateWorkItem = async (id: string, updates: Partial<WorkItem>) => {
    try {
      await updateDoc(doc(db, 'sistemas_work_items', id), {
        ...updates
      } as any);

      // Mirror to Knowledge base
      if (updates.pool_dados && updates.pool_dados.length > 0) {
        for (const item of updates.pool_dados) {
          const knowledgeItem: ConhecimentoItem = {
            id: item.id,
            titulo: item.nome || 'Sem título',
            tipo_arquivo: item.tipo === 'link' ? 'link' : (item.nome?.split('.').pop()?.toLowerCase() || 'unknown'),
            url_drive: item.valor,
            tamanho: 0,
            data_criacao: item.data_criacao,
            origem: { modulo: 'sistemas', id_origem: id },
            categoria: 'Sistemas'
          };
          setDoc(doc(db, 'conhecimento', item.id), knowledgeItem).catch(console.error);
        }
      }
      showToast("Item de trabalho atualizado!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar item.", "error");
    }
  };

  const handleFileUploadToDrive = async (file: File) => {
    try {
      setIsUploading(true);
      const reader = new FileReader();
      const base64Promise = new Promise<string>((resolve) => {
        reader.onload = () => {
          const base64 = (reader.result as string).split(',')[1];
          resolve(base64);
        };
      });
      reader.readAsDataURL(file);
      const fileContent = await base64Promise;

      const uploadFunc = httpsCallable(functions, 'upload_to_drive');
      const result = await uploadFunc({
        fileName: file.name,
        fileContent: fileContent,
        mimeType: file.type,
        folderId: appSettings.googleDriveFolderId
      });

      const data = result.data as { fileId: string, webViewLink: string };

      const newItem: PoolItem = {
        id: data.fileId,
        tipo: 'arquivo',
        valor: data.webViewLink,
        nome: file.name,
        data_criacao: new Date().toISOString()
      };

      return newItem;
    } catch (err) {
      console.error(err);
      showToast("Erro ao carregar para o Drive.", "error");
      return null;
    } finally {
      setIsUploading(false);
    }
  };

  useEffect(() => {
    const unsub = onSnapshot(collection(db, 'exames'), (snap) => {
      const data = snap.docs.map(d => ({ id: d.id, ...d.data() } as HealthExam));
      setExams(data);
    });
    return () => unsub();
  }, []);

  const handleDeleteWorkItem = async (id: string) => {
    const item = workItems.find(w => w.id === id);
    if (!item) return;

    try {
      await deleteDoc(doc(db, 'sistemas_work_items', id));

      pushToUndoStack("Excluir Log", async () => {
        const { id: _, ...data } = item;
        await setDoc(doc(db, 'sistemas_work_items', id), data);
      });

      showToast("Item de trabalho removido.", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover item.", "error");
    }
  };

  const handleArchiveIdea = async (id: string) => {
    try {
      const idea = brainstormIdeas.find(i => i.id === id);
      if (!idea) return;

      const newStatus = idea.status === 'archived' ? 'active' : 'archived';
      await updateDoc(doc(db, 'brainstorm_ideas', id), {
        status: newStatus
      });
      showToast(newStatus === 'archived' ? "Nota concluída e arquivada!" : "Nota restaurada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao processar nota.", "error");
    }
  };

  const handleAddTextIdea = async (text: string) => {
    try {
      await addDoc(collection(db, 'brainstorm_ideas'), {
        text,
        timestamp: new Date().toISOString(),
        status: 'active'
      });
      showToast("Nota registrada!", "success", undefined, [
        {
          // Ícone de Copiar
          label: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3" /></svg>,
          onClick: () => {
            navigator.clipboard.writeText(text);
            showToast("Conteúdo copiado!", "info");
          }
        },
        {
          // Ícone de Ir para Notas (Link Externo style)
          label: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>,
          onClick: () => {
            setActiveModule('acoes');
            setViewMode('ferramentas');
            setActiveFerramenta('brainstorming');
          }
        }
      ]);
    } catch (err) {
      console.error(err);
      showToast("Erro ao salvar nota.", "error");
    }
  };

  const handleAddKnowledgeLink = async (url: string, title: string) => {
    try {
      await addDoc(collection(db, 'conhecimento'), {
        titulo: title,
        tipo_arquivo: 'link',
        url_drive: url,
        tamanho: 0,
        data_criacao: new Date().toISOString(),
        origem: null
      });
      showToast("Link salvo com sucesso.", "success");
    } catch (e) {
      console.error(e);
      showToast("Erro ao salvar link.", "error");
    }
  };

  const handleSaveKnowledgeItem = async (item: Partial<ConhecimentoItem>) => {
    try {
      if (item.id) {
        await updateDoc(doc(db, 'conhecimento', item.id), item);
        showToast("Item atualizado.", "success");
      } else {
        await addDoc(collection(db, 'conhecimento'), {
          ...item,
          data_criacao: new Date().toISOString()
        });
        showToast("Item salvo.", "success");
      }
    } catch (e) {
      console.error(e);
      showToast("Erro ao salvar item.", "error");
    }
  };

  const handleProcessWithAI = async (id: string) => {
    const processarArquivoIA = httpsCallable(functions, 'processarArquivoIA');
    try {
      const result = await processarArquivoIA({ itemId: id });
      return result.data;
    } catch (error: any) {
      console.error("Erro no processamento IA:", error);
      return { success: false, error: error.message };
    }
  };

  const handleGenerateSlides = async (text: string) => {
    const gerarSlidesIA = httpsCallable(functions, 'gerarSlidesIA');
    try {
      const result = await gerarSlidesIA({ rascunho: text });
      return result.data;
    } catch (error: any) {
      console.error("Erro ao gerar slides:", error);
      throw error;
    }
  };

  const handleAddQuickLog = async (text: string, systemId: string) => {
    try {
      await handleCreateWorkItem(systemId, 'desenvolvimento', text, [], true);
      showToast("Log registrado!", "success", {
        label: "Ver sistema",
        onClick: () => {
          setActiveModule('acoes');
          setViewMode('sistemas-dev');
          setSelectedSystemId(systemId);
        }
      });
    } catch (err) {
      console.error(err);
      showToast("Erro ao registrar log.", "error");
    }
  };

  const handleDeleteIdea = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'brainstorm_ideas', id));
      showToast("Nota removida.", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover.", "error");
    }
  };

  const handleCreateTarefa = async (data: Partial<Tarefa>) => {
    try {
      setLoading(true);
      await addDoc(collection(db, 'tarefas'), {
        ...data,
        google_id: "", // Sinaliza que precisa de PUSH
        data_atualizacao: new Date().toISOString(),
        projeto: 'Google Tasks',
        prioridade: 'média',
        contabilizar_meta: data.categoria === 'CLC' || data.categoria === 'ASSISTÊNCIA',
        acompanhamento: [],
        entregas_relacionadas: []
      });

      if (convertingIdea) {
        await deleteDoc(doc(db, 'brainstorm_ideas', convertingIdea.id));
        setConvertingIdea(null);
        setTaskInitialData(null);
      }
      showToast("Nova ação criada!", 'success');
    } catch (err) {
      console.error("Erro ao criar tarefa:", err);
      showToast("Erro ao criar ação.", 'error');
    } finally {
      setLoading(false);
    }
  };



  useEffect(() => {
    setLoading(true);
    setError(null);

    // Listener para Tarefas
    const qTarefas = query(collection(db, 'tarefas'));
    const unsubscribeTarefas = onSnapshot(qTarefas, (snapshot) => {
      const dataT = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as Tarefa));
      setTarefas(dataT);
      setLoading(false);
    }, (err) => {
      console.error(err);
      setError("Erro ao conectar com o banco de dados (Tarefas).");
      setLoading(false);
    });

    // Listener para Atividades PGC
    const qAtividadesPGC = query(collection(db, 'atividades_pgc'));
    const unsubscribeAtividadesPGC = onSnapshot(qAtividadesPGC, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as AtividadeRealizada));
      setAtividadesPGC(data);
    });

    // Listener para Afastamentos
    const qAfastamentos = query(collection(db, 'afastamentos'));
    const unsubscribeAfastamentos = onSnapshot(qAfastamentos, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as Afastamento));
      setAfastamentos(data);
    });

    // Listener para Atividades (Entregas Legado/Config)
    const qAtividades = query(collection(db, 'atividades'));
    const unsubscribeAtividades = onSnapshot(qAtividades, (snapshot) => {
      const dataE = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as EntregaInstitucional));
      setEntregas(dataE);
    }, (err) => {
      console.error(err);
      setError("Erro ao conectar com o banco de dados (Atividades).");
    });


    const qUnidades = query(collection(db, 'unidades'));
    const unsubscribeUnidades = onSnapshot(qUnidades, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as { id: string, nome: string, palavras_chave?: string[] }));
      setUnidades(data);
    });



    return () => {
      unsubscribeTarefas();
      unsubscribeAtividades();
      unsubscribeAtividadesPGC();
      unsubscribeAfastamentos();
      unsubscribeUnidades();
    };
  }, []);

  const handleAddUnidade = async (nome: string) => {
    try {
      await addDoc(collection(db, 'unidades'), {
        nome: nome,
        palavras_chave: []
      });
      showToast(`Área ${nome} adicionada!`, 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao adicionar área.", 'error');
    }
  };

  const handleDeleteUnidade = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'unidades', id));
      showToast("Área removida.", 'info');
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover área.", 'error');
    }
  };

  const handleUpdateUnidade = async (id: string, updates: any) => {
    try {
      await updateDoc(doc(db, 'unidades', id), updates);
      showToast("Área atualizada!", 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar área.", 'error');
    }
  };

  useEffect(() => {
    const qPlanos = query(collection(db, 'planos_trabalho'));
    const unsubscribePlanos = onSnapshot(qPlanos, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as PlanoTrabalho));
      setPlanosTrabalho(data);
    });
    return () => unsubscribePlanos();
  }, []);

  useEffect(() => {
    const qBrainstorm = query(collection(db, 'brainstorm_ideas'));
    const unsubscribeBrainstorm = onSnapshot(qBrainstorm, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as BrainstormIdea));
      setBrainstormIdeas(data.sort((a, b) => b.timestamp.localeCompare(a.timestamp)));
    });

    const unsubscribeKnowledge = onSnapshot(collection(db, 'conhecimento'), (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as ConhecimentoItem));
      setKnowledgeItems(data);
    });

    return () => {
      unsubscribeBrainstorm();
      unsubscribeKnowledge();
    };
  }, []);


  const handleLinkTarefa = async (tarefaId: string, entregaId: string) => {
    try {
      const docRef = doc(db, 'tarefas', tarefaId);
      await updateDoc(docRef, {
        entregas_relacionadas: arrayUnion(entregaId)
      });
      showToast("Vínculo criado com sucesso!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao vincular tarefa.", "error");
    }
  };

  const handleUnlinkTarefa = async (tarefaId: string, entregaId: string) => {
    try {
      const docRef = doc(db, 'tarefas', tarefaId);
      await updateDoc(docRef, {
        entregas_relacionadas: arrayRemove(entregaId)
      });
      showToast("Vínculo removido!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover vínculo.", "error");
    }
  };

  const handleCreateEntregaFromPlan = async (item: PlanoTrabalhoItem): Promise<string | null> => {
    try {
      const docRef = await addDoc(collection(db, 'entregas'), {
        entrega: item.entrega,
        area: item.origem,
        unidade: item.unidade,
        mes: currentMonth,
        ano: currentYear
      });
      return docRef.id;
    } catch (err) {
      console.error(err);
      return null;
    }
  };

  // Health Handlers
  const handleUpdateHealthSettings = async (settings: HealthSettings) => {
    await setDoc(doc(db, 'health_settings', 'config'), settings);
    showToast("Meta de peso atualizada!", "success");
  };

  const handleAddHealthWeight = async (weight: number, date: string) => {
    await addDoc(collection(db, 'health_weights'), { weight, date });
    showToast("Peso registrado com sucesso!", "success");
  };

  const handleDeleteHealthWeight = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'health_weights', id));
      showToast("Registro de peso removido.", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover registro.", "error");
    }
  };

  const handleUpdateFinanceGoal = async (goal: FinanceGoal) => {
    try {
      await updateDoc(doc(db, 'finance_goals', goal.id), goal as any);
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar meta.", "error");
    }
  };

  const handleReorderFinanceGoals = async (reorderedGoals: FinanceGoal[]) => {
    try {
      const promises = reorderedGoals.map((goal, index) =>
        updateDoc(doc(db, 'finance_goals', goal.id), { priority: index + 1 })
      );
      await Promise.all(promises);
      showToast("Prioridades atualizadas!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao reordenar metas.", "error");
    }
  };

  const handleDeleteFinanceGoal = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'finance_goals', id));
      showToast("Meta removida!", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover meta.", "error");
    }
  };

  const handleUpdateHealthHabits = async (date: string, habits: Partial<DailyHabits>) => {
    await setDoc(doc(db, 'health_daily_habits', date), habits, { merge: true });
  };

  const handleMarkNotificationRead = (id: string) => {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, isRead: true } : n));
  };

  const handleDismissNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
    if (activePopup?.id === id) setActivePopup(null);
  };


  const stats = useMemo(() => ({
    total: tarefas.length,
    emAndamento: tarefas.filter(t => normalizeStatus(t.status) === 'em andamento').length,
    concluidas: tarefas.filter(t => normalizeStatus(t.status) === 'concluido').length,
    clc: tarefas.filter(t => t.categoria === 'CLC' && normalizeStatus(t.status) !== 'concluido').length,
    assistencia: tarefas.filter(t => t.categoria === 'ASSISTÊNCIA' && normalizeStatus(t.status) !== 'concluido').length,
    geral: tarefas.filter(t => t.categoria === 'GERAL' && normalizeStatus(t.status) !== 'concluido').length,
    semTag: tarefas.filter(t => (t.categoria === 'NÃO CLASSIFICADA' || !t.categoria) && normalizeStatus(t.status) !== 'concluido' && t.status !== 'excluído' as any).length,
  }), [tarefas]);

  const prioridadesHoje = useMemo(() => {
    const now = new Date();
    const todayStr = formatDateLocalISO(now);

    return tarefas.filter(t => {
      if (normalizeStatus(t.status) === 'concluido' || t.status === 'excluído' as any) return false;
      if (!t.data_limite || t.data_limite === "-" || t.data_limite === "0000-00-00") return false;
      return t.data_limite === todayStr;
    });
  }, [tarefas]);

  const filteredAndSortedTarefas = useMemo(() => {
    let result = [...tarefas];
    if (searchTerm) {
      const s = searchTerm.toLowerCase();
      if (s === 'filter:unclassified') {
        result = result.filter(t => (!t.categoria || t.categoria === 'NÃO CLASSIFICADA') && normalizeStatus(t.status) !== 'concluido');
      } else if (s === 'categoria:geral') {
        result = result.filter(t => t.categoria === 'GERAL');
      } else {
        result = result.filter(t => t.titulo?.toLowerCase().includes(s) || t.projeto?.toLowerCase().includes(s) || t.notas?.toLowerCase().includes(s));
      }
    }
    if (statusFilter.length > 0) {
      result = result.filter(t => 
        statusFilter.some(sf => normalizeStatus(t.status) === normalizeStatus(sf)) ||
        (searchTerm && normalizeStatus(t.status) === 'concluido')
      );
    }

    if (areaFilter !== 'TODAS') {
      const norm = (val: any) => (val || '').toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
      const filterNorm = norm(areaFilter);
      result = result.filter(t => {
        const cat = norm(t.categoria);
        if (filterNorm === 'CLC') return cat === 'CLC';
        if (filterNorm === 'ASSISTENCIA') return cat === 'ASSISTENCIA' || cat === 'ASSISTENCIA ESTUDANTIL';
        if (filterNorm === 'NAO CLASSIFICADA') return !t.categoria || cat === 'NAO CLASSIFICADA';
        return cat === filterNorm;
      });
    }

    // Sempre remove excluídos
    result = result.filter(t => t.status !== 'excluído' as any);

    // Remove tarefas de Gasto Semanal (exclusivas do Financeiro)
    result = result.filter(t => !t.titulo.toLowerCase().includes('gasto semanal'));

    // Se estiver na visão Geral (que agora é a que mostra tudo ou sem categoria)
    // Se viewMode for gallery (Dashboard), ele mostra tudo filtrado por status.
    // Se criarmos uma visão específica para sem classificação, podemos filtrar aqui.
    if (viewMode === 'gallery' && searchTerm === 'filter:unclassified') {
      result = result.filter(t => (!t.categoria || t.categoria === 'NÃO CLASSIFICADA') && normalizeStatus(t.status) !== 'concluido');
    }

    result.sort((a, b) => {
      const dVal = (t: Tarefa) => (!t.data_limite || t.data_limite === "-" || t.data_limite.trim() === "") ? (sortOption === 'date-asc' ? Infinity : -Infinity) : new Date(t.data_limite).getTime();
      const dateCompare = sortOption === 'date-asc' ? dVal(a) - dVal(b) : dVal(b) - dVal(a);
      if (dateCompare !== 0) return dateCompare;

      // Se as datas são iguais, usamos a ordem manual se existir
      if (a.ordem !== undefined && b.ordem !== undefined) return a.ordem - b.ordem;
      if (a.ordem !== undefined) return -1;
      if (b.ordem !== undefined) return 1;

      // Se não houver ordem manual, usamos prioridade
      const priorityOrder = { 'alta': 3, 'média': 2, 'baixa': 1 };
      const pA = priorityOrder[a.prioridade] || 0;
      const pB = priorityOrder[b.prioridade] || 0;
      if (pA !== pB) return pB - pA;

      // Se ainda empatar, usamos o horário
      if (a.horario_inicio && b.horario_inicio) return a.horario_inicio.localeCompare(b.horario_inicio);
      if (a.horario_inicio) return -1;
      if (b.horario_inicio) return 1;

      return 0;
    });
    return result;
  }, [tarefas, searchTerm, statusFilter, sortOption, areaFilter]);

  // Calcula tarefas não classificadas usando EXATAMENTE o mesmo filtro da exibição
  const unclassifiedTasksCount = useMemo(() => {
    return tarefas.filter(t =>
      (!t.categoria || t.categoria === 'NÃO CLASSIFICADA') &&
      normalizeStatus(t.status) !== 'concluido' &&
      t.status !== 'excluído' as any
    ).length;
  }, [tarefas]);

  const tarefasAgrupadas: Record<string, Tarefa[]> = useMemo(() => {
    const buckets = {
      atrasadas: [] as Tarefa[],
      hoje: [] as Tarefa[],
      amanha: [] as Tarefa[],
      estaSemana: [] as Tarefa[],
      esteMes: [] as Tarefa[],
      semData: [] as Tarefa[],
      concluidas: [] as Tarefa[]
    };
    const mesesFuturos: Record<string, { label: string, tasks: Tarefa[] }> = {};

    const now = new Date();
    // Reset hours to ensure clean comparisons
    now.setHours(0, 0, 0, 0);
    const todayStr = now.toLocaleDateString('en-CA'); // YYYY-MM-DD

    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toLocaleDateString('en-CA');

    // End of current week (Saturday)
    const endOfWeek = new Date(now);
    endOfWeek.setDate(now.getDate() + (6 - now.getDay()));
    const endOfWeekStr = endOfWeek.toLocaleDateString('en-CA');

    // End of current month
    const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    const endOfMonthStr = endOfMonth.toLocaleDateString('en-CA');

    filteredAndSortedTarefas.forEach(t => {
      // Se a tarefa está concluída, vai para o bucket de concluídas (útil na pesquisa)
      if (normalizeStatus(t.status) === 'concluido') {
        buckets.concluidas.push(t);
        return;
      }

      // Sem Data
      if (!t.data_limite || t.data_limite === "-" || t.data_limite === "0000-00-00") {
        buckets.semData.push(t);
        return;
      }

      // Check for valid date format to prevent errors
      if (!/^\d{4}-\d{2}-\d{2}$/.test(t.data_limite)) {
        buckets.semData.push(t);
        return;
      }

      if (t.data_limite < todayStr) {
        buckets.atrasadas.push(t);
      } else if (t.data_limite === todayStr) {
        buckets.hoje.push(t);
      } else if (t.data_limite === tomorrowStr) {
        buckets.amanha.push(t);
      } else if (t.data_limite <= endOfWeekStr) {
        buckets.estaSemana.push(t);
      } else if (t.data_limite <= endOfMonthStr) {
        buckets.esteMes.push(t);
      } else {
        // Future Months
        const parts = t.data_limite.split('-');
        const key = `${parts[0]}-${parts[1]}`; // sortable key YYYY-MM

        if (!mesesFuturos[key]) {
          const dateObj = new Date(Number(parts[0]), Number(parts[1]) - 1, 2);
          const monthName = dateObj.toLocaleString('pt-BR', { month: 'long', year: 'numeric' });
          const label = monthName.charAt(0).toUpperCase() + monthName.slice(1);
          mesesFuturos[key] = { label, tasks: [] };
        }
        mesesFuturos[key].tasks.push(t);
      }
    });

    // Build final object preserving desired order
    const finalGroups: Record<string, Tarefa[]> = {};

    if (buckets.atrasadas.length > 0) finalGroups["Atrasadas"] = buckets.atrasadas;
    if (buckets.hoje.length > 0) finalGroups["Hoje"] = buckets.hoje;
    if (buckets.amanha.length > 0) finalGroups["Amanhã"] = buckets.amanha;
    if (buckets.estaSemana.length > 0) finalGroups["Esta Semana"] = buckets.estaSemana;
    if (buckets.esteMes.length > 0) finalGroups["Este Mês"] = buckets.esteMes;

    // Sort future months chronologically
    Object.keys(mesesFuturos).sort().forEach(key => {
      finalGroups[mesesFuturos[key].label] = mesesFuturos[key].tasks;
    });

    if (buckets.semData.length > 0) finalGroups["Sem Prazo Definido"] = buckets.semData;
    if (buckets.concluidas.length > 0) finalGroups["Concluídas"] = buckets.concluidas;

    return finalGroups;
  }, [filteredAndSortedTarefas]);

  useEffect(() => {
    if (!hasAutoExpanded && Object.keys(tarefasAgrupadas).length > 0) {
      setExpandedSections([Object.keys(tarefasAgrupadas)[0]]);
      setHasAutoExpanded(true);
    }
  }, [tarefasAgrupadas, hasAutoExpanded]);

  const toggleSection = (label: string) => {
    setExpandedSections(prev =>
      prev.includes(label) ? prev.filter(s => s !== label) : [...prev, label]
    );
  };

  // No PGC, filtramos as tarefas pelo período selecionado (mês/ano)
  // No PGC, filtramos as tarefas pelo período selecionado (mês/ano)
  const pgcTasks: Tarefa[] = useMemo(() => {
    // Normalização agressiva para comparação de texto
    const norm = (val: any) => {
      if (!val) return "";
      return String(val).toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
    };

    return tarefas.filter(t => {
      if (t.status === 'excluído' as any) return false;

      const proj = norm(t.projeto);
      const cat = norm(t.categoria);

      // Identificadores das unidades PGD/PGC - Pelo PROJETO ou CATEGORIA
      const isCLC = proj.includes('CLC') || cat === 'CLC';
      const isASSIST = proj.includes('ASSIST') || proj.includes('ESTUDANTIL') || cat.includes('ASSISTENCIA');
      const isPgcUnit = isCLC || isASSIST;

      // Verifica se está vinculada a qualquer entrega institucional
      const linkedIds = Array.isArray(t.entregas_relacionadas) ? t.entregas_relacionadas.filter(id => !!id) : [];
      const isLinkedAtAll = linkedIds.length > 0;

      // Regra fundamental: Se não é unidade PGD e não foi vinculado manualmente, não entra no PGC
      if (!isPgcUnit && !isLinkedAtAll) return false;

      // Se estiver vinculado, aplicamos a regra de exibição temporal (mês atual)
      if (isLinkedAtAll) {
        if (!t.data_limite || t.data_limite === "-" || t.data_limite === "0000-00-00") return true;
        const parts = t.data_limite.split(/[-/]/);
        if (parts.length < 3) return true;

        let taskYear = parseInt(parts[0]);
        let taskMonth = parseInt(parts[1]) - 1;

        if (taskYear < 1000) {
          taskYear = parseInt(parts[2]);
          taskMonth = parseInt(parts[1]) - 1;
        }

        return taskMonth === currentMonth && taskYear === currentYear;
      }

      // Se for unidade PGD mas ainda não vinculado, aparece no PGC (staging area)
      return isPgcUnit;
    });
  }, [tarefas, currentMonth, currentYear]);

  const pgcEntregas: EntregaInstitucional[] = useMemo(() => entregas.filter(e => {
    return e.mes === currentMonth && e.ano === currentYear;
  }), [entregas, currentMonth, currentYear]);

  const pgcTasksAguardando: Tarefa[] = useMemo(() => {
    const currentDeliveryIds = pgcEntregas.map(e => e.id);
    const norm = (val: any) => (val || '').toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();

    return pgcTasks.filter(t => {
      // Regra 1: Deve ser da categoria CLC ou ASSISTÊNCIA
      const isCLC = t.categoria === 'CLC' || (t.projeto && norm(t.projeto).includes('CLC'));
      const isAssist = t.categoria === 'ASSISTÊNCIA' || (t.projeto && (norm(t.projeto).includes('ASSIST') || norm(t.projeto).includes('ESTUDANTIL')));

      if (!isCLC && !isAssist) return false;

      // Regra de Filtro por Data (Visualização Diária)
      // Se estiver na visão de dia, mostra APENAS o que está agendado para aquele dia específico
      if (calendarViewMode === 'day') {
        const targetDateStr = calendarDate.toLocaleDateString('en-CA');
        if (t.data_limite !== targetDateStr) return false;
      }

      // Regra 2: Verifica vínculos com entregas DO MÊS ATUAL
      const linkedIds = Array.isArray(t.entregas_relacionadas) ? t.entregas_relacionadas : [];
      const isLinkedToCurrent = linkedIds.some(id => currentDeliveryIds.includes(id));

      // Se JÁ estiver vinculado a uma entrega deste mês, não precisa aparecer na lista de "Aguardando"
      // POIS ela já aparecerá dentro do card da entrega correspondente.
      // Se estiver vinculado a entrega de OUTRO mês, deve aparecer aqui? 
      // O usuário disse: "todas as tarefas que tem a tag CLC ou a tag assistência estudantil devam constar nessa aba Audit PGC"
      // E "Se ela estiver vinculada a uma das atividades já cadastradas, ótimo, senão o sistema deve proporcionar uma forma inteligente de fazer essa vinculação."

      return !isLinkedToCurrent;
    });
  }, [pgcTasks, pgcEntregas, calendarViewMode, calendarDate]);

  const allUnidades = useMemo(() => {
    const fixed = ['CLC', 'Assistência Estudantil'];
    const dbUnidades = unidades.map(u => u.nome);
    return Array.from(new Set([...fixed, ...dbUnidades]));
  }, [unidades]);

  // Auditoria PGC - Heatmap de lacunas de registro
  const pgcAudit = useMemo(() => {
    const now = new Date();
    const workDays = getMonthWorkDays(currentYear, currentMonth);
    const gaps: Date[] = [];

    workDays.forEach(day => {
      // Ignorar dias futuros
      if (day > now) return;

      const dayStr = formatDateLocalISO(day);

      const hasActivity = atividadesPGC.some(a => {
        const start = a.data_inicio.split('T')[0];
        const end = a.data_fim?.split('T')[0] || start;
        return dayStr >= start && dayStr <= end;
      });

      const isAfastado = afastamentos.some(af => {
        const start = af.data_inicio.split('T')[0];
        const end = af.data_fim.split('T')[0];
        return dayStr >= start && dayStr <= end;
      });

      if (!hasActivity && !isAfastado) gaps.push(new Date(day));
    });

    return { gaps, totalWorkDays: workDays.length };
  }, [atividadesPGC, afastamentos]);

  if (authLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-400">Hermes está carregando...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-[#F8FAFC] flex flex-col items-center justify-center p-6">
        <div className="bg-white p-12 rounded-none md:rounded-[3rem] shadow-2xl border border-slate-100 max-w-md w-full text-center animate-in zoom-in-95">
          <div className="w-20 h-20 bg-slate-900 rounded-[2rem] flex items-center justify-center mx-auto mb-8 shadow-xl">
            <span className="text-white text-3xl font-black">H</span>
          </div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight mb-2">Hermes</h1>
          <p className="text-slate-500 text-sm font-medium mb-10 leading-relaxed">
            Bem-vindo ao seu ecossistema de produtividade e gestão à vista.
          </p>
          <button
            onClick={handleLogin}
            className="w-full bg-slate-900 text-white py-5 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-[0.2em] shadow-2xl shadow-slate-200 hover:bg-blue-600 transition-all active:scale-95 flex items-center justify-center gap-4"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.908 3.152-2.112 4.076-1.028.724-2.48 1.408-5.728 1.408-5.104 0-9.272-4.144-9.272-9.232s4.168-9.232 9.272-9.232c2.808 0 4.58 1.104 5.612 2.056l2.312-2.312c-1.936-1.824-4.52-3.112-7.924-3.112-6.524 0-12 5.424-12 12s5.476 12 12 12c3.552 0 6.228-1.172 8.528-3.564 2.376-2.376 3.128-5.704 3.128-8.32 0-.824-.068-1.552-.2-2.224h-11.456z" />
            </svg>
            Entrar com Google
          </button>

          <div className="mt-6 flex items-center justify-center gap-3">
            <input
              type="checkbox"
              id="remember-me"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer"
            />
            <label htmlFor="remember-me" className="text-[10px] font-black uppercase tracking-widest text-slate-400 cursor-pointer select-none hover:text-slate-600 transition-colors">
              Mantenha-me conectado
            </label>
          </div>
          <p className="text-[8px] font-black text-slate-300 uppercase tracking-widest mt-8">Secure Authentication via Firebase</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="min-h-screen bg-[#F8FAFC] flex flex-col md:flex-row relative">

        {/* Pop-up de Notificação */}
        {activePopup && (
          <div className="fixed bottom-8 left-4 right-4 md:left-8 md:right-auto z-[200] max-w-sm ml-auto mr-auto md:ml-0 md:mr-0 bg-white rounded-none md:rounded-[2.5rem] shadow-[0_30px_60px_rgba(0,0,0,0.25)] border border-slate-100 overflow-hidden animate-in slide-in-from-bottom-12 duration-500">
            <div className={`h-2 w-full ${activePopup.type === 'success' ? 'bg-emerald-500' :
              activePopup.type === 'warning' ? 'bg-amber-500' :
                activePopup.type === 'error' ? 'bg-rose-500' : 'bg-blue-600'
              }`} />
            <div className="p-8">
              <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em]">{activePopup.title}</span>
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse"></span>
                </div>
                <button onClick={() => setActivePopup(null)} className="text-slate-300 hover:text-slate-600 transition-colors p-1">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
              <p className="text-[11px] text-slate-500 leading-relaxed font-bold">{activePopup.message}</p>
              <div className="mt-6 flex gap-3">
                <button
                  onClick={() => setActivePopup(null)}
                  className="flex-1 px-5 py-3 bg-slate-100 text-slate-500 rounded-lg md:rounded-xl text-[9px] font-black uppercase tracking-widest transition-all hover:bg-slate-200"
                >
                  Entendido
                </button>
                {activePopup.link && (
                  <button
                    onClick={() => {
                      handleNotificationNavigate(activePopup.link);
                      setActivePopup(null);
                    }}
                    className="flex-1 px-5 py-3 bg-slate-900 text-white rounded-lg md:rounded-xl text-[9px] font-black uppercase tracking-widest transition-all hover:bg-slate-800 shadow-lg shadow-slate-200"
                  >
                    Ver Agora
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Sidebar Desktop */}
        <aside className={`hidden md:flex ${isSidebarRetracted ? 'w-24' : 'w-72'} bg-slate-900 text-white flex-col h-screen sticky top-0 overflow-y-auto shrink-0 z-50 shadow-2xl transition-all duration-300`}>
          <div className={`p-8 flex flex-col h-full ${isSidebarRetracted ? 'gap-8 items-center pt-10' : 'gap-10'}`}>
            <div
              className={`flex items-center gap-4 cursor-pointer hover:opacity-80 transition-opacity ${isSidebarRetracted ? 'flex-col' : ''}`}
              onClick={() => setIsSidebarRetracted(!isSidebarRetracted)}
            >
              <img src="/logo.png" alt="Hermes" className={`${isSidebarRetracted ? 'w-14 h-14' : 'w-12 h-12'} object-contain`} />
              {!isSidebarRetracted && (
                <div>
                  <h1 className="text-2xl font-black tracking-tighter">HERMES</h1>
                  <p className="text-[8px] font-black text-slate-500 uppercase tracking-widest leading-none">Management System</p>
                </div>
              )}
            </div>

            <nav className="flex flex-col gap-2">
              {[
                { id: 'dashboard', label: 'Dashboard', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>, active: viewMode === 'dashboard', onClick: () => { setActiveModule('dashboard'); setViewMode('dashboard'); } },
                { id: 'acoes', label: 'Ações', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>, active: activeModule === 'acoes' && (viewMode === 'gallery' || viewMode === 'pgc' || viewMode === 'licitacoes' || viewMode === 'assistencia'), onClick: () => { setActiveModule('acoes'); setViewMode('gallery'); } },
                { id: 'projetos', label: 'Projetos', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>, active: activeModule === 'projetos' && viewMode === 'projects', onClick: () => { setActiveModule('projetos'); setViewMode('projects'); } },
                { id: 'finance', label: 'Financeiro', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>, active: activeModule === 'financeiro', onClick: () => { setActiveModule('financeiro'); setViewMode('finance'); } },
                { id: 'saude', label: 'Saúde', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>, active: activeModule === 'saude', onClick: () => { setActiveModule('saude'); setViewMode('saude'); } },
                { id: 'sistemas', label: 'Sistemas', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>, active: viewMode === 'sistemas-dev', onClick: () => { setActiveModule('acoes'); setViewMode('sistemas-dev'); } },
                { id: 'conhecimento', label: 'Conhecimento', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>, active: viewMode === 'knowledge', onClick: () => { setActiveModule('acoes'); setViewMode('knowledge'); } },
                { id: 'ferramentas', label: 'Ferramentas', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>, active: viewMode === 'ferramentas', onClick: () => { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta(null); } },
              ].map(item => (
                <button
                  key={item.id}
                  onClick={item.onClick}
                  className={`flex items-center gap-4 px-6 py-4 rounded-2xl transition-all duration-300 group ${item.active ? 'bg-white text-slate-900 shadow-xl' : 'text-slate-400 hover:text-white hover:bg-white/5'} ${isSidebarRetracted ? 'justify-center' : ''}`}
                  title={isSidebarRetracted ? item.label : ''}
                >
                  <div className={`${item.active ? 'text-slate-900' : 'group-hover:scale-110 transition-transform duration-300'}`}>
                    {item.icon}
                  </div>
                  {!isSidebarRetracted && <span className="text-[11px] font-black uppercase tracking-widest">{item.label}</span>}
                </button>
              ))}
            </nav>

            <div className="mt-auto flex flex-col gap-6">
              <div className={`flex items-center gap-3 bg-white/5 p-4 rounded-2xl border border-white/5 ${isSidebarRetracted ? 'flex-col gap-4' : ''}`}>
                {isSidebarRetracted ? (
                  <>
                    <div
                      className="w-10 h-10 rounded-xl bg-slate-800 flex items-center justify-center font-black text-[10px] text-white border border-white/10 shadow-lg"
                      title={user?.displayName || "Usuário"}
                    >
                      {user?.displayName ? user.displayName.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2) : 'A'}
                    </div>
                    <button
                      onClick={handleLogout}
                      className="p-2 text-slate-500 hover:text-rose-400 transition-colors"
                      title="Sair do Sistema"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                      </svg>
                    </button>
                  </>
                ) : (
                  <>
                    {user?.photoURL ? (
                      <img src={user.photoURL} alt="Profile" className="w-10 h-10 rounded-xl shadow-sm border border-white/10" />
                    ) : (
                      <div className="w-10 h-10 rounded-xl bg-slate-800 flex items-center justify-center font-black text-xs text-white border border-white/10">
                        {user?.displayName ? user.displayName.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2) : 'A'}
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-[10px] font-black uppercase tracking-tight text-white truncate">{user?.displayName}</p>
                      <button
                        onClick={handleLogout}
                        className="text-[8px] font-black text-slate-500 hover:text-rose-400 uppercase tracking-widest transition-colors"
                      >
                        Sair do Sistema
                      </button>
                    </div>
                  </>
                )}
              </div>
              {!isSidebarRetracted && (
                <p className="text-center text-[8px] font-black text-slate-700 uppercase tracking-widest">
                  Hermes v2.5.0 • 2024
                </p>
              )}
            </div>
          </div>
        </aside>

        {/* Conteúdo Principal */}
        <div className="flex-1 flex flex-col relative min-h-screen">
          <>
            <header className="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-sm">
              <div className="max-w-[1400px] mx-auto px-4 md:px-8 py-3 md:py-4">
                {/* Mobile Header */}
                <div className="flex md:hidden items-center justify-between">
                  <div className="flex items-center gap-4">
                    <button
                      onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                      className="p-2 text-slate-700 hover:bg-slate-100 rounded-lg transition-all active:scale-95"
                      aria-label="Menu"
                    >
                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        {isMobileMenuOpen ? (
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                        ) : (
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" />
                        )}
                      </svg>
                    </button>
                    <div
                      onClick={() => { setActiveModule('dashboard'); setViewMode('dashboard'); }}
                      className="flex items-center cursor-pointer hover:opacity-80 transition-opacity"
                    >
                      <img src="/logo.png" alt="Hermes" className="w-9 h-9 object-contain" />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <SpeedDialMenu
                      notifications={notifications}
                      isSyncing={isSyncing}
                      isNotificationCenterOpen={isNotificationCenterOpen}
                      onOpenNotes={() => setIsQuickNoteModalOpen(true)}
                      onOpenLog={() => { setIsQuickLogModalOpen(true); setIsMobileMenuOpen(false); }}
                      onOpenShopping={() => { setIsShoppingAIModalOpen(true); setIsMobileMenuOpen(false); }}
                      onOpenTranscription={() => { setIsTranscriptionAIModalOpen(true); setIsMobileMenuOpen(false); }}
                      onToggleNotifications={() => setIsNotificationCenterOpen(prev => !prev)}
                      onSync={handleSync}
                      onOpenSettings={() => setIsSettingsModalOpen(true)}
                      onCloseNotifications={() => setIsNotificationCenterOpen(false)}
                      onMarkAsRead={handleMarkNotificationRead}
                      onDismiss={handleDismissNotification}
                      onUpdateOverdue={handleUpdateOverdueTasks}
                      onNavigate={handleNotificationNavigate}
                      onCreateAction={() => setIsCreateModalOpen(true)}
                    />
                    {viewMode !== 'ferramentas' && viewMode !== 'sistemas-dev' && viewMode !== 'knowledge' && viewMode !== 'saude' && viewMode !== 'finance' && viewMode !== 'dashboard' && viewMode !== 'projects' && (
                      <button
                        onClick={() => setIsCreateModalOpen(true)}
                        className="bg-slate-900 text-white p-1.5 rounded-lg md:rounded-xl shadow-lg hover:bg-slate-800 transition-all active:scale-95"
                        aria-label="Criar Ação"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                      </button>
                    )}
                  </div>
                </div>

                {/* Opções de Sub-módulo para Mobile (Ações / PGC) */}
                {(viewMode === 'gallery' || viewMode === 'pgc') && activeModule === 'acoes' && (
                  <div className="flex md:hidden items-center gap-2 mt-3 pt-3 border-t border-slate-100 animate-in slide-in-from-top-2 duration-300">
                    <button
                      onClick={() => {
                        setViewMode('gallery');
                        setSearchTerm('');
                      }}
                      className={`flex-1 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'gallery' ? 'bg-slate-900 text-white shadow-lg' : 'bg-slate-50 text-slate-500 hover:bg-slate-100'}`}
                    >
                      Ações
                    </button>
                    <button
                      onClick={() => setViewMode('pgc')}
                      className={`flex-1 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'pgc' ? 'bg-slate-900 text-white shadow-lg' : 'bg-slate-50 text-slate-500 hover:bg-slate-100'}`}
                    >
                      PGC
                    </button>
                  </div>
                )}

                {/* Opções de Financeiro para Mobile */}
                {viewMode === 'finance' && (
                  <div className="flex flex-col md:hidden gap-3 mt-3 pt-3 border-t border-slate-100 animate-in slide-in-from-top-2 duration-300">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 flex bg-slate-100 p-1 rounded-xl border border-slate-200">
                        <button
                          onClick={() => setFinanceActiveTab('dashboard')}
                          className={`flex-1 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${financeActiveTab === 'dashboard' ? 'bg-white text-slate-900 shadow-sm border border-slate-100' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                          Visão Geral
                        </button>
                        <button
                          onClick={() => setFinanceActiveTab('fixed')}
                          className={`flex-1 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${financeActiveTab === 'fixed' ? 'bg-white text-slate-900 shadow-sm border border-slate-100' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                          Obrigações
                        </button>
                      </div>
                      <button
                        onClick={() => setIsFinanceSettingsOpen(!isFinanceSettingsOpen)}
                        className={`p-2.5 rounded-xl transition-all border ${isFinanceSettingsOpen ? 'bg-slate-900 text-white border-slate-900 shadow-lg' : 'bg-white text-slate-400 border-slate-200 hover:bg-slate-50 hover:text-slate-900 shadow-sm'}`}
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                      </button>
                    </div>

                    <div className="flex items-center justify-between bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden h-11">
                      <button
                        onClick={() => {
                          const newMonth = currentMonth === 0 ? 11 : currentMonth - 1;
                          const newYear = currentMonth === 0 ? currentYear - 1 : currentYear;
                          setCurrentMonth(newMonth);
                          setCurrentYear(newYear);
                        }}
                        className="px-4 h-full flex items-center hover:bg-slate-50 text-slate-400 hover:text-slate-900 transition-all border-r border-slate-100"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M15 19l-7-7 7-7" /></svg>
                      </button>
                      <div className="px-4 text-center">
                        <div className="text-xs font-black text-slate-900 capitalize tracking-tight">
                          {new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(new Date(currentYear, currentMonth))}
                        </div>
                      </div>
                      <button
                        onClick={() => {
                          const newMonth = currentMonth === 11 ? 0 : currentMonth + 1;
                          const newYear = currentMonth === 11 ? currentYear + 1 : currentYear;
                          setCurrentMonth(newMonth);
                          setCurrentYear(newYear);
                        }}
                        className="px-4 h-full flex items-center hover:bg-slate-50 text-slate-400 hover:text-slate-900 transition-all border-l border-slate-100"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                      </button>
                    </div>
                  </div>
                )}

                {/* Desktop Header */}
                <div className="hidden md:flex items-center justify-between gap-4">
                  <div className="flex items-center gap-6">
                    <div className="flex items-center gap-3">
                      {/* Botão de voltar removido pois agora temos sidebar */}
                      <div
                        onClick={() => { setActiveModule('dashboard'); setViewMode('dashboard'); }}
                        className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity"
                      >
                        <h1 className="text-xl font-black tracking-tighter text-slate-900 uppercase">
                          {viewMode === 'projects' ? 'Projetos' :
                            viewMode === 'knowledge' ? 'Conhecimento' :
                              viewMode === 'sistemas-dev' ? 'Sistemas' :
                                viewMode === 'ferramentas' ? 'Ferramentas' :
                                  activeModule === 'dashboard' ? 'Dashboard' :
                                    activeModule === 'acoes' ? 'Ações' :
                                      activeModule === 'financeiro' ? 'Financeiro' :
                                        activeModule === 'saude' ? 'Saúde' : 'Hermes'}
                        </h1>
                      </div>
                    </div>
                    {viewMode === 'projects' && (
                      <div className="flex items-center gap-3 animate-in fade-in slide-in-from-left duration-500">
                        <button
                          onClick={() => setIsProjectCreateModalOpen(true)}
                          className="px-4 py-2 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-200 text-xs font-black uppercase tracking-widest flex items-center gap-2"
                          title="Criar Projeto"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                          Criar Projeto
                        </button>
                        <button
                          onClick={handleExportModule}
                          className="p-2 bg-white border border-slate-200 text-slate-400 rounded-xl hover:bg-slate-50 transition-all shadow-sm"
                          title="Exportar Markdown"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4v12" /></svg>
                        </button>
                      </div>
                    )}
                    {['finance', 'saude', 'gallery', 'sistemas-dev'].includes(viewMode) && (
                      <div className="flex items-center gap-3 animate-in fade-in slide-in-from-left duration-500">
                        <button
                          onClick={handleExportModule}
                          className="p-2 bg-white border border-slate-200 text-slate-400 rounded-xl hover:bg-slate-50 transition-all shadow-sm"
                          title="Exportar Markdown"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4v12" /></svg>
                        </button>
                      </div>
                    )}

                    {viewMode !== 'ferramentas' && viewMode !== 'sistemas-dev' && viewMode !== 'knowledge' && viewMode !== 'projects' && activeModule !== 'financeiro' && activeModule !== 'saude' && activeModule !== 'dashboard' && (
                      <nav className="flex bg-slate-100 p-1 rounded-lg md:rounded-xl border border-slate-200">
                        <button
                          onClick={() => {
                            setViewMode('gallery');
                            setSearchTerm('');
                          }}
                          className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'gallery' && !searchTerm ? 'bg-white text-slate-900 shadow-sm border border-slate-100' : 'text-slate-500 hover:text-slate-800'}`}
                        >
                          Ações
                        </button>
                        <button onClick={() => setViewMode('pgc')} className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'pgc' ? 'bg-slate-900 text-white shadow-lg' : 'text-slate-500 hover:text-slate-800'}`}>PGC</button>
                      </nav>
                    )}
                  </div>

                  {viewMode === 'sistemas-dev' && !selectedSystemId && (
                    <div className="flex items-center gap-3">
                      <button
                        onClick={handleCopyBacklog}
                        className="bg-violet-600 text-white px-5 py-2 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-violet-700 transition-all flex items-center gap-3"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>
                        Copiar <span className="hidden lg:inline">Tudo</span>
                      </button>
                      <button
                        onClick={() => {
                          setSettingsTab('sistemas');
                          setIsSettingsModalOpen(true);
                        }}
                        className="bg-slate-900 text-white px-5 py-2 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all flex items-center gap-2"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                        Novo <span className="hidden lg:inline">Sistema</span>
                      </button>
                    </div>
                  )}


                  {/* Finance Controls */}
                  {viewMode === 'finance' && (
                    <div className="flex items-center gap-4">
                      <div className="flex bg-slate-100 p-1 rounded-lg border border-slate-200">
                        <button
                          onClick={() => setFinanceActiveTab('dashboard')}
                          className={`px-4 py-1.5 text-[10px] uppercase font-black rounded-lg transition-all ${financeActiveTab === 'dashboard' ? 'bg-white shadow-sm text-slate-900 border border-slate-100' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                          Visão Geral
                        </button>
                        <button
                          onClick={() => setFinanceActiveTab('fixed')}
                          className={`px-4 py-1.5 text-[10px] uppercase font-black rounded-lg transition-all ${financeActiveTab === 'fixed' ? 'bg-white shadow-sm text-slate-900 border border-slate-100' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                          Rendas e Obrigações
                        </button>
                      </div>

                      <div className="flex items-center bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                        <button
                          onClick={() => {
                            const newMonth = currentMonth === 0 ? 11 : currentMonth - 1;
                            const newYear = currentMonth === 0 ? currentYear - 1 : currentYear;
                            setCurrentMonth(newMonth);
                            setCurrentYear(newYear);
                          }}
                          className="p-2 hover:bg-slate-50 text-slate-400 hover:text-slate-900 transition-all border-r border-slate-100"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M15 19l-7-7 7-7" /></svg>
                        </button>
                        <div className="px-3 text-center min-w-[100px]">
                          <div className="text-[10px] font-black text-slate-900 capitalize leading-none tracking-tight">
                            {new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(new Date(currentYear, currentMonth))}
                          </div>
                        </div>
                        <button
                          onClick={() => {
                            const newMonth = currentMonth === 11 ? 0 : currentMonth + 1;
                            const newYear = currentMonth === 11 ? currentYear + 1 : currentYear;
                            setCurrentMonth(newMonth);
                            setCurrentYear(newYear);
                          }}
                          className="p-2 hover:bg-slate-50 text-slate-400 hover:text-slate-900 transition-all border-l border-slate-100"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                        </button>
                      </div>

                      <button
                        onClick={() => setIsFinanceSettingsOpen(!isFinanceSettingsOpen)}
                        className={`p-2 rounded-xl transition-all border ${isFinanceSettingsOpen ? 'bg-slate-900 text-white border-slate-900 shadow-lg' : 'bg-white text-slate-400 border-slate-200 hover:bg-slate-50 hover:text-slate-900 shadow-sm'}`}
                        title="Configurações Financeiras"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                      </button>
                    </div>
                  )}

                  {/* Standard Action Buttons (Search, Sync, Create) */}
                  {viewMode !== 'ferramentas' && viewMode !== 'sistemas-dev' && viewMode !== 'knowledge' && viewMode !== 'saude' && viewMode !== 'finance' && viewMode !== 'dashboard' && viewMode !== 'projects' && (
                    <div className="flex items-center gap-4">
                      {activeModule !== 'dashboard' && (
                        <div className="hidden lg:flex items-center bg-slate-50 border border-slate-200 rounded-lg md:rounded-xl px-4 py-2 w-64 group focus-within:ring-2 focus-within:ring-blue-500 focus-within:bg-white transition-all">
                          <svg className="w-4 h-4 text-slate-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                          <input type="text" placeholder="Pesquisar..." className="bg-transparent border-none outline-none text-xs font-bold text-slate-900 w-full" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
                        </div>
                      )}
                      <button
                        onClick={() => setIsCreateModalOpen(true)}
                        className="bg-slate-900 text-white px-5 py-2 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 shadow-lg hover:bg-slate-800 transition-all active:scale-95"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                        Criar Ação
                      </button>
                    </div>
                  )}
                  {/* Global Header Actions — Speed Dial */}
                  <SpeedDialMenu
                    notifications={notifications}
                    isSyncing={isSyncing}
                    isNotificationCenterOpen={isNotificationCenterOpen}
                    onOpenNotes={() => setIsQuickNoteModalOpen(true)}
                    onOpenLog={() => setIsQuickLogModalOpen(true)}
                    onOpenShopping={() => setIsShoppingAIModalOpen(true)}
                    onOpenTranscription={() => setIsTranscriptionAIModalOpen(true)}
                    onToggleNotifications={() => setIsNotificationCenterOpen(prev => !prev)}
                    onSync={handleSync}
                    onOpenSettings={() => setIsSettingsModalOpen(true)}
                    onCloseNotifications={() => setIsNotificationCenterOpen(false)}
                    onMarkAsRead={handleMarkNotificationRead}
                    onDismiss={handleDismissNotification}
                    onUpdateOverdue={handleUpdateOverdueTasks}
                    onNavigate={handleNotificationNavigate}
                    onCreateAction={() => setIsCreateModalOpen(true)}
                  />
                </div>
              </div>

              {/* Mobile Menu Drawer */}
              {isMobileMenuOpen && (
                <div className="md:hidden border-t border-slate-200 bg-white shadow-2xl animate-in slide-in-from-top-4 duration-300">
                  <nav className="flex flex-col p-4 gap-2">
                    {[
                      { label: '🏠 Dashboard', active: viewMode === 'dashboard', onClick: () => { setActiveModule('dashboard'); setViewMode('dashboard'); } },
                      { label: '📊 Ações', active: activeModule === 'acoes' && (viewMode === 'gallery' || viewMode === 'licitacoes' || viewMode === 'assistencia'), onClick: () => { setActiveModule('acoes'); setViewMode('gallery'); } },
                      { label: '🚀 Projetos', active: activeModule === 'projetos' && viewMode === 'projects', onClick: () => { setActiveModule('projetos'); setViewMode('projects'); } },
                      { label: '📋 PGC', active: activeModule === 'acoes' && viewMode === 'pgc', onClick: () => { setActiveModule('acoes'); setViewMode('pgc'); } },
                      { label: '💰 Financeiro', active: activeModule === 'financeiro', onClick: () => { setActiveModule('financeiro'); setViewMode('finance'); } },
                      { label: '❤️ Saúde', active: activeModule === 'saude', onClick: () => { setActiveModule('saude'); setViewMode('saude'); } },
                      { label: '💻 Sistemas', active: viewMode === 'sistemas-dev', onClick: () => { setActiveModule('acoes'); setViewMode('sistemas-dev'); } },
                      { label: '📚 Conhecimento', active: viewMode === 'knowledge', onClick: () => { setActiveModule('acoes'); setViewMode('knowledge'); } },
                      { label: '🛠️ Ferramentas', active: viewMode === 'ferramentas', onClick: () => { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta(null); } },
                    ].map((item, idx) => (
                      <button
                        key={idx}
                        onClick={() => {
                          item.onClick();
                          setIsMobileMenuOpen(false);
                        }}
                        className={`px-6 py-4 rounded-2xl text-sm font-black uppercase tracking-widest transition-all ${item.active ? 'bg-slate-900 text-white shadow-lg' : 'bg-slate-50 text-slate-600'}`}
                      >
                        {item.label}
                      </button>
                    ))}

                    <div className="grid grid-cols-2 gap-2 mt-4 pt-4 border-t border-slate-100">
                      <button
                        onClick={() => {
                          handleSync();
                          setIsMobileMenuOpen(false);
                        }}
                        className="px-4 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest bg-blue-50 text-blue-700 flex items-center justify-center gap-2"
                      >
                        <svg className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                        {isSyncing ? 'Sync...' : 'Sync'}
                      </button>
                      <button
                        onClick={() => {
                          setIsSettingsModalOpen(true);
                          setIsMobileMenuOpen(false);
                        }}
                        className="px-4 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest bg-slate-100 text-slate-600 flex items-center justify-center gap-2"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                        Config
                      </button>
                      <button
                        onClick={handleLogout}
                        className="col-span-2 px-4 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest bg-rose-50 text-rose-600 flex items-center justify-center gap-2 mt-2"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
                        Sair da Conta
                      </button>
                    </div>
                  </nav>
                </div>
              )}
            </header>

            <div className={`mx-auto w-full ${viewMode === 'dashboard' ? 'max-w-[1600px] px-0 py-0' : 'max-w-[1400px] px-0 md:px-8 py-6'}`}>
              {/* Painel de Estatísticas e Filtros - APENAS NA VISÃO GERAL */}
              <main className={viewMode === 'dashboard' ? '' : 'mb-20'}>
                {viewMode === 'dashboard' ? (
                  <DashboardView
                    tarefas={tarefas}
                    financeTransactions={financeTransactions}
                    financeSettings={financeSettings}
                    fixedBills={fixedBills}
                    incomeEntries={incomeEntries}
                    healthWeights={healthWeights}
                    healthDailyHabits={healthDailyHabits}
                    healthSettings={healthSettings}
                    unidades={unidades}
                    sistemasDetalhes={sistemasDetalhes}
                    workItems={workItems}
                    currentMonth={currentMonth}
                    currentYear={currentYear}
                    onNavigate={handleDashboardNavigate}
                    onOpenBacklog={handleCopyBacklog}
                  />
                ) : viewMode === 'gallery' ? (
                  <>
                    {/* Mobile Search Bar */}
                    <div className="lg:hidden px-4 mb-6">
                      <div className="flex items-center bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-sm focus-within:ring-2 focus-within:ring-blue-500 transition-all">
                        <svg className="w-5 h-5 text-slate-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                        <input
                          type="text"
                          placeholder="Pesquisar ações..."
                          className="bg-transparent border-none outline-none text-sm font-bold text-slate-900 w-full placeholder:text-slate-400"
                          value={searchTerm === 'filter:unclassified' ? '' : searchTerm}
                          onChange={(e) => setSearchTerm(e.target.value)}
                        />
                        {searchTerm && searchTerm !== 'filter:unclassified' && (
                          <button onClick={() => setSearchTerm('')} className="ml-2 text-slate-400 hover:text-slate-600">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-col md:flex-row items-center justify-between mb-8 gap-4 px-4 md:px-0">
                      {/* Linha de Filtros e Ações Globais */}
                      <div className="flex items-center justify-between w-full gap-2">
                        {/* Lado Esquerdo: Filtro de Área */}
                        <div className="relative group flex-shrink-1 min-w-0 max-w-[140px] md:max-w-none md:min-w-[180px]">
                          <select
                            value={areaFilter}
                            onChange={(e) => setAreaFilter(e.target.value)}
                            className="h-11 w-full appearance-none bg-white pl-3 md:pl-4 pr-8 md:pr-10 rounded-xl border border-slate-200 text-[10px] font-black uppercase tracking-tight md:tracking-widest text-slate-700 outline-none focus:ring-2 focus:ring-slate-900 shadow-sm hover:border-slate-300 transition-all cursor-pointer truncate"
                          >
                            <option value="TODAS">TODAS</option>
                            <option value="CLC">CLC</option>
                            <option value="ASSISTÊNCIA">ASSISTÊNCIA</option>
                            <option value="GERAL">GERAL</option>
                            <option value="NÃO CLASSIFICADA">PENDENTES</option>
                            {unidades.filter(u => !['CLC', 'ASSISTÊNCIA', 'ASSISTÊNCIA ESTUDANTIL'].includes(u.nome.toUpperCase())).map(u => (
                              <option key={u.id} value={u.nome.toUpperCase()}>{u.nome}</option>
                            ))}
                          </select>
                          <div className="absolute inset-y-0 right-0 flex items-center px-2 md:px-3 pointer-events-none text-slate-400">
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" /></svg>
                          </div>
                        </div>

                        {/* Lado Direito: Modos de Visualização e Organizar Dia */}
                        <div className="flex items-center gap-1 md:gap-2 flex-shrink-0">
                          {searchTerm !== 'filter:unclassified' && (
                            <div className="h-11 bg-slate-100 p-1 rounded-xl shadow-inner inline-flex border border-slate-200">
                              <button
                                onClick={() => setDashboardViewMode('list')}
                                className={`px-2 md:px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${dashboardViewMode === 'list' ? 'bg-white shadow-md text-slate-900' : 'text-slate-400 hover:text-slate-600'}`}
                              >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" /></svg>
                                <span className="hidden lg:inline">Lista</span>
                              </button>
                              <button
                                onClick={() => setDashboardViewMode('calendar')}
                                className={`px-2 md:px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${dashboardViewMode === 'calendar' ? 'bg-white shadow-md text-slate-900' : 'text-slate-400 hover:text-slate-600'}`}
                              >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2-2v12a2 2 0 002 2z" /></svg>
                                <span className="hidden lg:inline">Calendário</span>
                              </button>
                            </div>
                          )}

                          <button
                            onClick={() => {
                              setDashboardViewMode('calendar');
                              setCalendarViewMode('day');
                              setCalendarDate(new Date());
                            }}
                            className="h-11 bg-slate-900 text-white px-3 md:px-6 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all flex items-center justify-center gap-2 active:scale-95"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                            <span className="hidden sm:inline">Organizar</span>
                          </button>
                        </div>
                      </div>
                    </div>

                    {dashboardViewMode === 'calendar' ? (
                      <CalendarView
                        tasks={filteredAndSortedTarefas}
                        googleEvents={googleCalendarEvents}
                        viewMode={calendarViewMode}
                        currentDate={calendarDate}
                        onDateChange={setCalendarDate}
                        onTaskClick={setSelectedTask}
                        onViewModeChange={setCalendarViewMode}
                        onTaskUpdate={handleUpdateTarefa}
                        onExecuteTask={(t) => { setSelectedTask(t); setTaskModalMode('execute'); }}
                        onReorderTasks={handleReorderTasks}
                        showToast={showToast}
                      />
                    ) : (
                      <>
                        {searchTerm === 'filter:unclassified' ? (
                          <div className="animate-in bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl">
                            <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex flex-col md:flex-row md:items-center justify-between gap-4">
                              <h3 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-3">
                                <span className="w-2 h-8 bg-rose-600 rounded-full"></span>
                                Organização Rápida
                              </h3>

                              {selectedTaskIds.length > 0 && (
                                <div className="flex items-center gap-2 bg-slate-900 p-2 rounded-none md:rounded-2xl animate-in slide-in-from-top-4">
                                  <span className="text-[9px] font-black text-white uppercase tracking-widest px-4">Classificar ({selectedTaskIds.length}):</span>
                                  <button onClick={() => handleBatchTag('CLC')} className="bg-blue-600 hover:bg-blue-700 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-lg md:rounded-xl transition-all">CLC</button>
                                  <button onClick={() => handleBatchTag('ASSISTÊNCIA')} className="bg-emerald-600 hover:bg-emerald-700 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-lg md:rounded-xl transition-all">Assistência</button>
                                  <button onClick={() => handleBatchTag('GERAL')} className="bg-slate-500 hover:bg-slate-600 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-lg md:rounded-xl transition-all">Geral</button>
                                </div>
                              )}
                            </div>

                            <div className="overflow-x-auto">
                              {/* Desktop Table */}
                              <table className="w-full text-left hidden md:table">
                                <thead className="bg-slate-50 border-b border-slate-200">
                                  <tr>
                                    <th className="px-8 py-4 w-12 text-center text-[10px] font-black text-slate-400 uppercase tracking-widest italic">#</th>
                                    <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Descrição da Tarefa</th>
                                    <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-40 text-center">Data Limite</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-50">
                                  {filteredAndSortedTarefas.map((task) => (
                                    <tr
                                      key={task.id}
                                      onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); }}
                                      className={`hover:bg-slate-50 transition-colors cursor-pointer ${selectedTaskIds.includes(task.id) ? 'bg-blue-50/30' : ''}`}
                                    >
                                      <td className="px-8 py-4 text-center">
                                        <input
                                          type="checkbox"
                                          checked={selectedTaskIds.includes(task.id)}
                                          onChange={(e) => {
                                            e.stopPropagation();
                                            setSelectedTaskIds(prev => prev.includes(task.id) ? prev.filter(id => id !== task.id) : [...prev, task.id]);
                                          }}
                                          className="w-5 h-5 rounded-lg border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer"
                                        />
                                      </td>
                                      <td className="px-8 py-4">
                                        <div className="flex items-center gap-2 flex-wrap">
                                          <div className="text-[13px] font-bold text-slate-800 hover:text-blue-600 transition-colors leading-snug">
                                            {task.titulo}
                                          </div>
                                          {task.sync_status === 'new' && (
                                            <span className="text-[8px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-sm animate-pulse">
                                              Novo
                                            </span>
                                          )}
                                          {task.sync_status === 'updated' && (
                                            <span className="text-[8px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-amber-400 to-orange-500 text-white shadow-sm">
                                              Atualizada
                                            </span>
                                          )}
                                        </div>
                                      </td>
                                      <td className="px-8 py-4 text-center text-[10px] font-black text-slate-400 uppercase">
                                        {formatDate(task.data_limite)}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>

                              {/* Mobile Card View */}
                              <div className="md:hidden divide-y divide-slate-50">
                                {filteredAndSortedTarefas.map((task) => (
                                  <div
                                    key={task.id}
                                    onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); }}
                                    className={`p-6 space-y-4 hover:bg-slate-50 transition-colors cursor-pointer ${selectedTaskIds.includes(task.id) ? 'bg-blue-50/30' : ''}`}
                                  >
                                    <div className="flex items-start gap-4">
                                      <input
                                        type="checkbox"
                                        checked={selectedTaskIds.includes(task.id)}
                                        onChange={(e) => {
                                          e.stopPropagation();
                                          setSelectedTaskIds(prev => prev.includes(task.id) ? prev.filter(id => id !== task.id) : [...prev, task.id]);
                                        }}
                                        className="w-6 h-6 rounded-lg border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer shrink-0 mt-1"
                                      />
                                      <div className="flex-1 space-y-2">
                                        <div className="text-sm font-bold text-slate-800 leading-snug">
                                          {task.titulo}
                                        </div>
                                        <div className="flex items-center gap-2 flex-wrap">
                                          <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest bg-slate-100 px-2 py-0.5 rounded">
                                            {formatDate(task.data_limite)}
                                          </div>
                                          {task.sync_status === 'new' && (
                                            <span className="text-[7px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-sm animate-pulse">
                                              Novo
                                            </span>
                                          )}
                                          {task.sync_status === 'updated' && (
                                            <span className="text-[7px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-amber-400 to-orange-500 text-white shadow-sm">
                                              Atualizada
                                            </span>
                                          )}
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>

                              {filteredAndSortedTarefas.length === 0 && (
                                <div className="py-20 text-center text-slate-300 font-black uppercase tracking-widest italic border-t border-slate-50">
                                  Tudo classificado! Bom trabalho.
                                </div>
                              )}
                            </div>
                          </div>

                        ) : (
                          <div className="animate-in border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl bg-white">
                            {Object.keys(tarefasAgrupadas).length > 0 ? (
                              Object.entries(tarefasAgrupadas).map(([label, tasks]: [string, Tarefa[]]) => (
                                <div
                                  key={label}
                                  className="border-b last:border-b-0 border-slate-200 transition-colors"
                                  onDragOver={(e) => {
                                    e.preventDefault();
                                    e.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.05)';
                                  }}
                                  onDragLeave={(e) => {
                                    e.currentTarget.style.backgroundColor = '';
                                  }}
                                  onDrop={(e) => {
                                    e.preventDefault();
                                    e.currentTarget.style.backgroundColor = '';
                                    const taskId = e.dataTransfer.getData('task-id');
                                    if (taskId) {
                                      const date = getBucketStartDate(label);
                                      if (date || label === 'Sem Prazo Definido') {
                                        handleUpdateTarefa(taskId, { data_limite: date });
                                      }
                                    }
                                  }}
                                >
                                  <button
                                    onClick={() => toggleSection(label)}
                                    className="w-full px-6 py-3 bg-transparent border-b border-slate-100 flex items-center justify-between hover:bg-slate-50 transition-colors group"
                                  >
                                    <div className="flex items-center gap-3">
                                      <span className="text-xs font-black text-slate-400 uppercase tracking-[0.2em]">{label}</span>
                                      <span className="text-[10px] font-bold text-slate-300">({tasks.length})</span>
                                    </div>
                                    <svg className={`w-4 h-4 text-slate-300 transition-transform duration-300 ${expandedSections.includes(label) ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                                    </svg>
                                  </button>

                                  {expandedSections.includes(label) && (
                                    <div className="animate-in origin-top">
                                      {tasks.map(task => (
                                        <div
                                          key={task.id}
                                          draggable
                                          onDragStart={(e) => {
                                            e.dataTransfer.setData('task-id', task.id);
                                            e.currentTarget.style.opacity = '0.5';
                                          }}
                                          onDragEnd={(e) => {
                                            e.currentTarget.style.opacity = '1';
                                          }}
                                          onDragOver={(e) => e.preventDefault()}
                                          onDrop={(e) => {
                                            e.preventDefault();
                                            e.stopPropagation();
                                            const draggedId = e.dataTransfer.getData('task-id');
                                            if (draggedId && draggedId !== task.id) {
                                              handleReorderTasks(draggedId, task.id, label);
                                            }
                                          }}
                                        >
                                          <RowCard
                                            task={task}
                                            highlighted={label === 'Hoje' && tasks.filter(t => normalizeStatus(t.status) !== 'concluido')[0]?.id === task.id}
                                            onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); }}
                                            onToggle={handleToggleTarefaStatus}
                                            onDelete={handleDeleteTarefa}
                                            onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                                            onUpdateToToday={handleUpdateToToday}
                                          />
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              ))
                            ) : (
                              <div className="py-24 text-center bg-white">
                                <p className="text-slate-300 font-black text-xl uppercase tracking-widest">Sem demandas encontradas</p>
                              </div>
                            )}
                          </div>
                        )}

                        <div className="mt-12 space-y-6">
                          <button
                            onClick={() => setIsCompletedTasksOpen(!isCompletedTasksOpen)}
                            className="w-full flex items-center gap-4 group cursor-pointer"
                          >
                            <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
                            <div className="flex items-center gap-2 text-slate-400 group-hover:text-slate-600 transition-colors">
                              <h3 className="text-[10px] font-black uppercase tracking-[0.3em]">Concluídas Recentemente</h3>
                              <svg className={`w-4 h-4 transition-transform duration-300 ${isCompletedTasksOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                              </svg>
                            </div>
                            <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
                          </button>

                          {isCompletedTasksOpen && (
                            <div className="bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-sm opacity-60 hover:opacity-100 transition-opacity animate-in slide-in-from-top-4 duration-300">
                              {tarefas.filter(t => normalizeStatus(t.status) === 'concluido' && t.status !== 'excluído' as any).length > 0 ? (
                                tarefas
                                  .filter(t => normalizeStatus(t.status) === 'concluido' && t.status !== 'excluído' as any)
                                  .sort((a, b) => (b.data_conclusao || '').localeCompare(a.data_conclusao || ''))
                                  .slice(0, 10)
                                  .map(t => (
                                    <RowCard
                                      key={t.id}
                                      task={t}
                                      onClick={() => { setSelectedTask(t); setTaskModalMode('execute'); }}
                                      onToggle={handleToggleTarefaStatus}
                                      onDelete={handleDeleteTarefa}
                                      onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                                      onUpdateToToday={handleUpdateToToday}
                                    />
                                  ))
                              ) : (
                                <div className="py-12 text-center">
                                  <p className="text-slate-300 font-black text-[10px] uppercase tracking-widest italic">Nenhuma tarefa concluída</p>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </>
                ) : (viewMode === 'licitacoes' || viewMode === 'assistencia') ? (
                  <CategoryView
                    tasks={filteredAndSortedTarefas}
                    viewMode={viewMode}
                    onSelectTask={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                    onExecuteTask={(t) => { setSelectedTask(t); setTaskModalMode('execute'); }}
                  />
                ) : viewMode === 'sistemas' ? (
                  <div className="animate-in space-y-8">
                    <div className="bg-white p-8 rounded-none md:rounded-[2rem] border border-slate-200 shadow-xl">
                      <h3 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-3">
                        <span className="w-2 h-8 bg-amber-500 rounded-full"></span>
                        Desenvolvimento de Sistemas
                      </h3>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                      {(sistemasAtivos.length > 0
                        ? sistemasAtivos
                        : Array.from(new Set(tarefas.filter(t => t.categoria === 'SISTEMAS').map(t => t.sistema || 'OUTROS')))
                      ).map(sistema => (
                        <div key={sistema} className="bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-lg flex flex-col">
                          <div className="p-6 bg-slate-900 text-white flex justify-between items-center">
                            <h4 className="text-xs font-black uppercase tracking-[0.2em]">{sistema}</h4>
                            <span className="bg-white/20 px-3 py-1 rounded-full text-[10px] font-black">{tarefas.filter(t => t.categoria === 'SISTEMAS' && (t.sistema || 'OUTROS') === sistema).length}</span>
                          </div>
                          <div className="p-6 space-y-4 flex-1 bg-slate-50/50">
                            {tarefas.filter(t => t.categoria === 'SISTEMAS' && (t.sistema || 'OUTROS') === sistema).map(t => (
                              <div key={t.id} className="bg-white p-4 rounded-lg md:rounded-xl border border-slate-200 shadow-sm hover:border-amber-400 transition-all cursor-pointer" onClick={() => setSelectedTask(t)}>
                                <div className={`text-[8px] font-black mb-1.5 uppercase ${STATUS_COLORS[normalizeStatus(t.status)] || ''} border-none p-0 bg-transparent`}>
                                  {t.status}
                                </div>
                                <div className="text-[11px] font-bold text-slate-700 leading-tight">{t.titulo}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                ) : viewMode === 'saude' ? (
                  <HealthView
                    weights={healthWeights}
                    dailyHabits={healthDailyHabits}
                    settings={healthSettings}
                    onUpdateSettings={handleUpdateHealthSettings}
                    onAddWeight={handleAddHealthWeight}
                    onDeleteWeight={handleDeleteHealthWeight}
                    onUpdateHabits={handleUpdateHealthHabits}
                    exams={exams}
                    onAddExam={async (exam, files) => {
                      let poolItems: PoolItem[] = [];

                      if (files.length > 0 && appSettings.googleDriveFolderId) {
                        try {
                          showToast("Enviando arquivos para o Drive...", "info");
                          for (const file of files) {
                            const item = await handleFileUploadToDrive(file);
                            if (item) poolItems.push(item);
                          }
                        } catch (e) {
                          console.error(e);
                          showToast("Erro no upload de um ou mais arquivos.", "error");
                        }
                      }

                      const examDoc = await addDoc(collection(db, 'exames'), {
                        ...exam,
                        pool_dados: poolItems,
                        data_criacao: new Date().toISOString()
                      });

                      // Mirror to Knowledge base
                      if (poolItems.length > 0) {
                        for (const item of poolItems) {
                          const knowledgeItem: ConhecimentoItem = {
                            id: item.id,
                            titulo: item.nome || 'Sem título',
                            tipo_arquivo: item.tipo === 'link' ? 'link' : (item.nome?.split('.').pop()?.toLowerCase() || 'unknown'),
                            url_drive: item.valor,
                            tamanho: 0,
                            data_criacao: item.data_criacao,
                            origem: { modulo: 'saude', id_origem: examDoc.id },
                            categoria: 'Saúde'
                          };
                          await setDoc(doc(db, 'conhecimento', item.id), knowledgeItem);
                        }
                      }

                      showToast("Registro de saúde adicionado e indexado ao Drive.", "success");
                    }}
                    onDeleteExam={async (id) => {
                      showConfirm("Confirmar Exclusão", "Deseja realmente remover este registro de saúde?", async () => {
                        await deleteDoc(doc(db, 'exames', id));
                        showToast("Registro removido.", "info");
                      });
                    }}
                    onUpdateExam={async (id, updates) => {
                      await updateDoc(doc(db, 'exames', id), updates);
                      showToast("Registro atualizado.", "success");
                    }}
                  />
                ) : viewMode === 'ferramentas' ? (
                  <FerramentasView
                    ideas={brainstormIdeas}
                    onDeleteIdea={handleDeleteIdea}
                    onArchiveIdea={handleArchiveIdea}
                    onAddTextIdea={handleAddTextIdea}
                    onUpdateIdea={handleUpdateIdea}
                    onConvertToLog={(idea) => {
                      setConvertingIdea(idea);
                      setIsSystemSelectorOpen(true);
                    }}
                    onConvertToTask={handleConvertToTask}
                    activeTool={activeFerramenta}
                    setActiveTool={setActiveFerramenta}
                    isAddingText={isBrainstormingAddingText}
                    setIsAddingText={setIsBrainstormingAddingText}
                    showToast={showToast}
                    showAlert={showAlert}
                  />
                ) : viewMode === 'projects' ? (
                  <ProjectsView
                    projects={projects}
                    isCreating={isProjectCreateModalOpen}
                    onCloseCreate={() => setIsProjectCreateModalOpen(false)}
                    onCreateProject={handleCreateProject}
                  />
                ) : viewMode === 'finance' ? (
                  <FinanceView
                    transactions={financeTransactions}
                    goals={(() => {
                      const totalSavings = fixedBills
                        .filter(b => b.category === 'Poupança' && b.isPaid)
                        .reduce((acc, curr) => acc + curr.amount, 0);

                      const emergencyCurrent = financeSettings.emergencyReserveCurrent || 0;
                      let remaining = Math.max(0, totalSavings + emergencyCurrent - (financeSettings.emergencyReserveTarget || 0));
                      // Note: The logic here is a bit tricky. If "Poupança" bills are the ONLY thing that fills goals,
                      // and emergency reserve is a manual pot, then typically goals = totalSavings if emergency is full.
                      // But if emergency is manual, maybe the user wants: Remaining = total_saved_in_savings_bills.
                      // Let's assume goals are filled by "Poupança" items, but only if the manual emergency reserve is >= target.

                      const isEmergencyFull = emergencyCurrent >= (financeSettings.emergencyReserveTarget || 0);
                      let availableForGoals = isEmergencyFull ? totalSavings : 0;

                      return [...financeGoals].sort((a, b) => a.priority - b.priority).map(goal => {
                        const allocated = Math.min(availableForGoals, goal.targetAmount);
                        availableForGoals -= allocated;
                        return { ...goal, currentAmount: allocated };
                      });
                    })()}
                    emergencyReserve={{
                      target: financeSettings.emergencyReserveTarget || 0,
                      current: financeSettings.emergencyReserveCurrent || 0
                    }}
                    settings={financeSettings}
                    currentMonth={currentMonth}
                    currentYear={currentYear}
                    onMonthChange={(m, y) => {
                      setCurrentMonth(m);
                      setCurrentYear(y);
                    }}
                    currentMonthTotal={financeTransactions.filter(t => {
                      const d = new Date(t.date);
                      return d.getMonth() === currentMonth && d.getFullYear() === currentYear;
                    }).reduce((acc, curr) => acc + curr.amount, 0)}
                    currentMonthIncome={incomeEntries.filter(e => {
                      return e.month === currentMonth && e.year === currentYear;
                    }).reduce((acc, curr) => acc + curr.amount, 0)}
                    fixedBills={fixedBills}
                    billRubrics={billRubrics}
                    incomeEntries={incomeEntries}
                    incomeRubrics={incomeRubrics}
                    onAddRubric={async (rubric) => { await addDoc(collection(db, 'bill_rubrics'), rubric); }}
                    onUpdateRubric={async (rubric) => { await updateDoc(doc(db, 'bill_rubrics', rubric.id), rubric as any); }}
                    onDeleteRubric={async (id) => { await deleteDoc(doc(db, 'bill_rubrics', id)); }}
                    onAddIncomeRubric={async (rubric) => { await addDoc(collection(db, 'income_rubrics'), rubric); }}
                    onUpdateIncomeRubric={async (rubric) => { await updateDoc(doc(db, 'income_rubrics', rubric.id), rubric as any); }}
                    onDeleteIncomeRubric={async (id) => { await deleteDoc(doc(db, 'income_rubrics', id)); }}
                    onAddIncomeEntry={async (entry) => { await addDoc(collection(db, 'income_entries'), { ...entry, month: currentMonth, year: currentYear, status: 'active' }); }}
                    onUpdateIncomeEntry={async (entry) => { await updateDoc(doc(db, 'income_entries', entry.id), entry as any); }}
                    onDeleteIncomeEntry={async (id) => { await updateDoc(doc(db, 'income_entries', id), { status: 'deleted' }); }}
                    onUpdateSettings={(newSettings) => setDoc(doc(db, 'finance_settings', 'config'), newSettings)}
                    onAddGoal={(goal) => addDoc(collection(db, 'finance_goals'), { ...goal, priority: financeGoals.length + 1 })}
                    onUpdateGoal={handleUpdateFinanceGoal}
                    onDeleteGoal={handleDeleteFinanceGoal}
                    onReorderGoals={handleReorderFinanceGoals}
                    onAddBill={async (bill) => { await addDoc(collection(db, 'fixed_bills'), { ...bill, month: currentMonth, year: currentYear }); }}
                    onUpdateBill={async (bill) => { await updateDoc(doc(db, 'fixed_bills', bill.id), bill as any); }}
                    onDeleteBill={async (id) => { await deleteDoc(doc(db, 'fixed_bills', id)); }}
                    onAddTransaction={async (t) => { await addDoc(collection(db, 'finance_transactions'), { ...t, status: 'active' }); }}
                    onUpdateTransaction={async (t) => { await updateDoc(doc(db, 'finance_transactions', t.id), t as any); }}
                    onDeleteTransaction={async (id) => { await updateDoc(doc(db, 'finance_transactions', id), { status: 'deleted' }); }}
                    activeTab={financeActiveTab}
                    setActiveTab={setFinanceActiveTab}
                    isSettingsOpen={isFinanceSettingsOpen}
                    setIsSettingsOpen={setIsFinanceSettingsOpen}
                  />

                ) : viewMode === 'knowledge' ? (
                  <KnowledgeView
                    items={knowledgeItems}
                    onDeleteItem={async (id) => { await deleteDoc(doc(db, 'conhecimento', id)); }}
                    onUploadFile={handleUploadKnowledgeFile}
                    onAddLink={handleAddKnowledgeLink}
                    onSaveItem={handleSaveKnowledgeItem}
                    onProcessWithAI={handleProcessWithAI}
                    onGenerateSlides={handleGenerateSlides}
                    showConfirm={showConfirm}
                    allTasks={tarefas}
                    allWorkItems={workItems}
                  />
                ) : viewMode === 'sistemas-dev' ? (
                  <div className="space-y-8 animate-in fade-in duration-500 pb-20">
                    {!selectedSystemId ? (
                      /* VISÃO GERAL - LISTA DE SISTEMAS */
                      <>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-8 p-3 md:p-0 pt-8">
                          {unidades.filter(u => u.nome.startsWith('SISTEMA:')).map(unit => {
                            const sysDetails = sistemasDetalhes.find(s => s.id === unit.id) || {
                              id: unit.id,
                              nome: unit.nome.replace('SISTEMA:', '').trim(),
                              status: 'ideia' as SistemaStatus,
                              data_criacao: new Date().toISOString(),
                              data_atualizacao: new Date().toISOString()
                            };
                            const systemName = unit.nome.replace('SISTEMA:', '').trim();
                            const ajustesPendentes = workItems.filter(w => w.sistema_id === unit.id && !w.concluido).length;

                            return (
                              <button
                                key={unit.id}
                                onClick={() => setSelectedSystemId(unit.id)}
                                className="bg-white border border-slate-200 rounded-2xl md:rounded-[2.5rem] p-6 md:p-8 text-left shadow-sm md:shadow-xl hover:shadow-md md:hover:shadow-2xl hover:border-violet-300 transition-all group relative overflow-hidden"
                              >
                                <div className="absolute top-0 right-0 w-32 h-32 bg-violet-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                                <div className="relative z-10 space-y-6">
                                  <div className="flex justify-between items-start">
                                    <div className="w-14 h-14 bg-violet-100 text-violet-600 rounded-none md:rounded-2xl flex items-center justify-center group-hover:scale-110 transition-transform">
                                      <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                                    </div>
                                    <span className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest ${sysDetails.status === 'producao' ? 'bg-emerald-100 text-emerald-700' :
                                      sysDetails.status === 'desenvolvimento' ? 'bg-blue-100 text-blue-700' :
                                        sysDetails.status === 'testes' ? 'bg-amber-100 text-amber-700' :
                                          'bg-slate-100 text-slate-500'
                                      }`}>
                                      {sysDetails.status === 'prototipacao' ? 'Prototipação' :
                                        sysDetails.status === 'producao' ? 'Produção' :
                                          sysDetails.status}
                                    </span>
                                  </div>
                                  <div>
                                    <h3 className="text-xl font-black text-slate-900 mb-1 group-hover:text-violet-700 transition-colors">{systemName}</h3>
                                    <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                                      Atualizado em {formatDate(sysDetails.data_atualizacao?.split('T')[0] || formatDateLocalISO(new Date()))}
                                    </p>
                                  </div>
                                  <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
                                    <span className="text-xs font-bold text-slate-500">{ajustesPendentes} ajustes pendentes</span>
                                    <div className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center group-hover:bg-violet-500 group-hover:text-white transition-colors">
                                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
                                    </div>
                                  </div>
                                </div>
                              </button>
                            );
                          })}

                          {unidades.filter(u => u.nome.startsWith('SISTEMA:')).length === 0 && (
                            <div className="col-span-full text-center py-20 bg-slate-50 rounded-none md:rounded-[2.5rem] border-2 border-dashed border-slate-200">
                              <p className="text-slate-400 font-bold text-lg mb-2">Nenhum sistema cadastrado</p>
                              <button onClick={() => { setIsSettingsModalOpen(true); }} className="bg-slate-900 text-white px-6 py-3 rounded-lg md:rounded-xl font-bold uppercase tracking-widest text-xs hover:bg-slate-800 transition-all mt-4">
                                Ir para Configurações
                              </button>
                            </div>
                          )}
                        </div>
                      </>
                    ) : (
                      /* VISÃO DETALHADA - SISTEMA SELECIONADO */
                      (() => {
                        const unit = unidades.find(u => u.id === selectedSystemId);
                        if (!unit) return null;

                        const sysDetails = sistemasDetalhes.find(s => s.id === unit.id) || {
                          id: unit.id,
                          nome: unit.nome.replace('SISTEMA:', '').trim(),
                          status: 'ideia' as SistemaStatus,
                          data_criacao: new Date().toISOString(),
                          data_atualizacao: new Date().toISOString()
                        };

                        const systemName = unit.nome.replace('SISTEMA:', '').trim();
                        const systemWorkItems = workItems.filter(w => w.sistema_id === unit.id);
                        const ajustesPendentesCount = systemWorkItems.filter(w => !w.concluido).length;

                        const steps: SistemaStatus[] = ['ideia', 'prototipacao', 'desenvolvimento', 'testes', 'producao'];
                        const currentStepIndex = steps.indexOf(sysDetails.status);

                        return (
                          <div className="animate-in fade-in slide-in-from-bottom-8 duration-500">
                            {/* Navigation */}
                            <button
                              onClick={() => setSelectedSystemId(null)}
                              className="mb-8 px-6 md:px-0 flex items-center gap-2 text-slate-500 hover:text-slate-800 font-bold text-xs uppercase tracking-widest transition-colors"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
                              Voltar para Lista
                            </button>

                            <div className="bg-white border border-slate-200 rounded-none md:rounded-[2.5rem] overflow-hidden shadow-xl">
                              {/* Header Detalhado */}
                              <div className="hidden md:block bg-slate-900 p-8 md:p-12 text-white relative overflow-hidden">
                                <div className="absolute top-0 right-0 w-64 h-64 bg-violet-500/20 rounded-full -mr-20 -mt-20 blur-3xl"></div>
                                <div className="relative z-10 flex flex-col md:flex-row md:items-end justify-between gap-8">
                                  <div className="space-y-4">
                                    <div className="inline-flex items-center gap-2 bg-white/10 px-3 py-1 rounded-lg backdrop-blur-sm border border-white/10">
                                      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                                      <span className="text-[10px] font-black uppercase tracking-widest">
                                        {sysDetails.status === 'prototipacao' ? 'Prototipação' :
                                          sysDetails.status === 'producao' ? 'Produção' :
                                            sysDetails.status}
                                      </span>
                                    </div>
                                    <h2 className="text-4xl md:text-5xl font-black tracking-tight">{systemName}</h2>
                                  </div>
                                  <div className="text-right">
                                    <div className="text-3xl font-black text-violet-400">{ajustesPendentesCount}</div>
                                    <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Ajustes Pendentes</div>
                                  </div>
                                </div>
                              </div>

                              {/* Status Stepper */}
                              <div className="bg-slate-50 border-b border-slate-100 p-4 md:p-10 flex flex-col items-center gap-4 md:gap-8">
                                <div className="text-center">
                                  <h2 className="text-lg md:text-3xl font-black text-slate-900 tracking-tight uppercase">{systemName}</h2>
                                  <div className="w-8 h-1 bg-violet-500 mx-auto mt-2 rounded-full"></div>
                                </div>

                                <div className="flex flex-wrap items-center justify-center bg-slate-200/50 p-1 rounded-xl md:rounded-2xl gap-1 w-full md:w-auto">
                                  {steps.map((step, idx) => {
                                    const isActive = sysDetails.status === step;
                                    const stepLabels: Record<string, string> = {
                                      ideia: 'Ideia',
                                      prototipacao: 'Protótipo',
                                      desenvolvimento: 'Dev',
                                      testes: 'Testes',
                                      producao: 'Produção'
                                    };
                                    return (
                                      <React.Fragment key={step}>
                                        <button
                                          onClick={() => handleUpdateSistema(unit.id, { status: step })}
                                          className={`flex-1 md:flex-none px-2 md:px-4 py-2 rounded-lg md:rounded-xl text-[8px] md:text-[9px] font-black uppercase tracking-widest transition-all ${isActive
                                            ? 'bg-violet-600 text-white shadow-lg'
                                            : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'
                                            }`}
                                        >
                                          {stepLabels[step]}
                                        </button>
                                        {idx < steps.length - 1 && (
                                          <div className="hidden md:flex items-center text-slate-300 px-1">
                                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                                          </div>
                                        )}
                                      </React.Fragment>
                                    );
                                  })}
                                </div>
                              </div>

                              <div className="p-0 md:p-8 grid grid-cols-1 lg:grid-cols-3 gap-0 md:gap-12">
                                {/* Coluna 2: Links e Recursos (Topo no mobile) */}
                                <div className="lg:col-span-1 order-1 md:order-1 space-y-0 md:space-y-8">
                                  <div className="p-4 md:p-0">
                                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4 flex items-center gap-2">
                                      <span className="w-1 h-3 bg-violet-500 rounded-full"></span>
                                      Recursos
                                    </h4>
                                  </div>

                                  <div className="grid grid-cols-4 md:grid-cols-1 gap-2 md:gap-6 px-4 md:px-0 mb-8 md:mb-0">
                                    {/* Repositório */}
                                    <button
                                      onClick={() => setEditingResource({ field: 'repositorio_principal', label: 'Repositório', value: sysDetails.repositorio_principal || '' })}
                                      className="group bg-slate-900 p-4 md:p-6 rounded-2xl md:rounded-3xl border border-slate-800 hover:border-slate-600 hover:shadow-xl transition-all text-center md:text-left flex flex-col items-center md:items-stretch justify-center md:justify-between aspect-square md:aspect-auto md:min-h-[120px] relative overflow-hidden"
                                    >
                                      <div className="absolute top-0 right-0 w-24 h-24 bg-violet-500/10 rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-500"></div>
                                      <div className="relative z-10 space-y-2 md:space-y-3">
                                        <div className="w-8 h-8 md:w-10 md:h-10 bg-white/10 text-white rounded-lg flex items-center justify-center mx-auto md:mx-0">
                                          <svg className="w-4 h-4 md:w-5 md:h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" /></svg>
                                        </div>
                                        <h5 className="text-[8px] md:text-xs font-black text-white uppercase tracking-widest leading-none">Repo</h5>
                                      </div>
                                      <div className="hidden md:block relative z-10">
                                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{sysDetails.repositorio_principal ? 'Editar' : 'Configurar'}</span>
                                      </div>
                                    </button>

                                    {/* Documentação */}
                                    <button
                                      onClick={() => setEditingResource({ field: 'link_documentacao', label: 'Documentação', value: sysDetails.link_documentacao || '' })}
                                      className="group bg-white p-4 md:p-6 rounded-2xl md:rounded-3xl border border-slate-200 hover:border-violet-300 hover:shadow-xl transition-all text-center md:text-left flex flex-col items-center md:items-stretch justify-center md:justify-between aspect-square md:aspect-auto md:min-h-[120px] relative overflow-hidden"
                                    >
                                      <div className="absolute top-0 right-0 w-24 h-24 bg-violet-500/5 rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-500"></div>
                                      <div className="relative z-10 space-y-2 md:space-y-3">
                                        <div className="w-8 h-8 md:w-10 md:h-10 bg-violet-100 text-violet-600 rounded-lg flex items-center justify-center mx-auto md:mx-0">
                                          <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                        </div>
                                        <h5 className="text-[8px] md:text-xs font-black text-slate-900 uppercase tracking-widest leading-none">Docs</h5>
                                      </div>
                                      <div className="hidden md:block relative z-10">
                                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{sysDetails.link_documentacao ? 'Editar' : 'Configurar'}</span>
                                      </div>
                                    </button>

                                    {/* AI Studio */}
                                    <button
                                      onClick={() => setEditingResource({ field: 'link_google_ai_studio', label: 'AI Studio', value: sysDetails.link_google_ai_studio || '' })}
                                      className="group bg-white p-4 md:p-6 rounded-2xl md:rounded-3xl border border-slate-200 hover:border-blue-300 hover:shadow-xl transition-all text-center md:text-left flex flex-col items-center md:items-stretch justify-center md:justify-between aspect-square md:aspect-auto md:min-h-[120px] relative overflow-hidden"
                                    >
                                      <div className="absolute top-0 right-0 w-24 h-24 bg-blue-500/5 rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-500"></div>
                                      <div className="relative z-10 space-y-2 md:space-y-3">
                                        <div className="w-8 h-8 md:w-10 md:h-10 bg-blue-100 text-blue-600 rounded-lg flex items-center justify-center mx-auto md:mx-0">
                                          <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                        </div>
                                        <h5 className="text-[8px] md:text-xs font-black text-slate-900 uppercase tracking-widest leading-none">AI</h5>
                                      </div>
                                      <div className="hidden md:block relative z-10">
                                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{sysDetails.link_google_ai_studio ? 'Editar' : 'Configurar'}</span>
                                      </div>
                                    </button>

                                    {/* Link Hospedado */}
                                    <button
                                      onClick={() => setEditingResource({ field: 'link_hospedado', label: 'Hospedagem', value: sysDetails.link_hospedado || '' })}
                                      className="group bg-emerald-50 p-4 md:p-6 rounded-2xl md:rounded-3xl border border-emerald-100 hover:border-emerald-300 hover:shadow-xl transition-all text-center md:text-left flex flex-col items-center md:items-stretch justify-center md:justify-between aspect-square md:aspect-auto md:min-h-[120px] relative overflow-hidden"
                                    >
                                      <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/10 rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-500"></div>
                                      <div className="relative z-10 space-y-2 md:space-y-3">
                                        <div className="w-8 h-8 md:w-10 md:h-10 bg-emerald-100 text-emerald-600 rounded-lg flex items-center justify-center mx-auto md:mx-0">
                                          <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>
                                        </div>
                                        <h5 className="text-[8px] md:text-xs font-black text-emerald-900 uppercase tracking-widest leading-none">App</h5>
                                      </div>
                                      <div className="hidden md:block relative z-10">
                                        <span className="text-[10px] font-bold text-emerald-600/60 uppercase tracking-widest">{sysDetails.link_hospedado ? 'Editar' : 'Configurar'}</span>
                                      </div>
                                    </button>
                                  </div>
                                </div>

                                {/* Coluna 1: Logs de Trabalho (Abaixo no mobile) */}
                                <div className="lg:col-span-2 order-2 md:order-2 space-y-0 md:space-y-6">
                                  <div className="bg-white border-0 md:border border-slate-200 rounded-none md:rounded-[2.5rem] overflow-hidden flex flex-col min-h-[400px] md:min-h-[600px] shadow-none md:shadow-sm">
                                    {/* Novo Log Input */}
                                    <div className="p-6 md:p-8 border-b border-slate-100 bg-slate-50">
                                      <div className="flex flex-col gap-6">
                                        <div className="flex items-center justify-between gap-4">
                                          <div className="flex items-center gap-2">
                                            <div className="p-1.5 bg-violet-600 text-white rounded-lg">
                                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                            </div>
                                            <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Dev Log</h4>
                                          </div>
                                        </div>

                                        <div className="flex flex-col gap-4">
                                          <div className="relative">
                                            <WysiwygEditor
                                              value={newLogText}
                                              onChange={setNewLogText}
                                              placeholder="O que foi feito no sistema?"
                                              className="bg-white min-h-[120px] pb-10"
                                            />
                                            <div className="absolute right-4 top-4 flex flex-col gap-2">
                                              <button
                                                onClick={isRecordingLog ? stopLogRecording : startLogRecording}
                                                disabled={isProcessingLog}
                                                className={`p-3 rounded-xl transition-all ${isRecordingLog
                                                  ? 'bg-emerald-600 text-white animate-pulse shadow-lg'
                                                  : isProcessingLog
                                                    ? 'bg-violet-100 text-violet-600 cursor-wait'
                                                    : 'bg-slate-100 text-slate-400 hover:text-violet-600'
                                                  }`}
                                                title="Transcrever áudio"
                                              >
                                                {isProcessingLog ? (
                                                  <div className="w-5 h-5 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
                                                ) : isRecordingLog ? (
                                                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
                                                ) : (
                                                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                                                )}
                                              </button>
                                            </div>

                                            <label className={`absolute left-3 bottom-2 p-2 rounded-xl transition-all ${isUploading ? 'bg-violet-100 animate-pulse pointer-events-none' : 'text-slate-400 hover:text-violet-600 hover:bg-violet-50'} cursor-pointer`}>
                                              <input
                                                type="file"
                                                accept="image/*"
                                                className="hidden"
                                                onChange={async (e) => {
                                                  const file = e.target.files?.[0];
                                                  if (file) {
                                                    const item = await handleFileUploadToDrive(file);
                                                    if (item) setNewLogAttachments(prev => [...prev, item]);
                                                  }
                                                }}
                                              />
                                              {isUploading ? (
                                                <div className="w-4 h-4 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
                                              ) : (
                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                                              )}
                                            </label>
                                          </div>
                                          <div className="flex flex-wrap gap-2">
                                            {newLogAttachments.map((at, i) => (
                                              <div key={i} className="relative group/at">
                                                <img src={at.valor} alt="preview" className="w-16 h-16 object-cover rounded-lg border border-slate-200" />
                                                <button
                                                  onClick={() => setNewLogAttachments(prev => prev.filter((_, idx) => idx !== i))}
                                                  className="absolute -top-1 -right-1 bg-rose-500 text-white rounded-full p-0.5 opacity-0 group-hover/at:opacity-100 transition-all z-10"
                                                >
                                                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                                </button>
                                              </div>
                                            ))}
                                            <label className={`w-16 h-16 border-2 border-dashed border-slate-200 rounded-lg hidden md:flex items-center justify-center cursor-pointer hover:border-violet-400 hover:bg-violet-50 transition-all ${isUploading ? 'animate-pulse pointer-events-none' : ''}`}>
                                              <input
                                                type="file"
                                                accept="image/*"
                                                className="hidden"
                                                onChange={async (e) => {
                                                  const file = e.target.files?.[0];
                                                  if (file) {
                                                    const item = await handleFileUploadToDrive(file);
                                                    if (item) setNewLogAttachments(prev => [...prev, item]);
                                                  }
                                                }}
                                              />
                                              {isUploading ? (
                                                <div className="w-4 h-4 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
                                              ) : (
                                                <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                                              )}
                                            </label>
                                          </div>
                                          <button
                                            onClick={() => {
                                              handleCreateWorkItem(unit.id, newLogTipo, newLogText, newLogAttachments);
                                              setNewLogText('');
                                              setNewLogAttachments([]);
                                            }}
                                            disabled={!newLogText.trim()}
                                            className="w-full bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50 disabled:grayscale"
                                          >
                                            Registrar
                                          </button>
                                        </div>
                                      </div>
                                    </div>

                                    {/* Listagem de Logs */}
                                    <div className="block flex-1 overflow-y-auto p-4 md:p-8 bg-white space-y-8 pb-32">
                                      {/* Ativos (Não concluídos) */}
                                      <div className="space-y-4">
                                        <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest border-l-4 border-violet-500 pl-3">Logs Ativos</h5>
                                        {systemWorkItems.filter(w => !w.concluido).sort((a, b) => new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime()).map(log => (
                                          <div key={log.id} className="group bg-slate-50 border border-slate-100 rounded-none md:rounded-3xl p-6 hover:border-violet-200 hover:bg-white transition-all">
                                            <div className="flex flex-col md:flex-row items-start justify-between gap-4 md:gap-6">
                                              <div className="flex-1 space-y-2 w-full">
                                                <div className="flex items-center gap-3">
                                                  <span className={`text-[8px] font-black px-2 py-0.5 rounded uppercase tracking-wider ${log.tipo === 'desenvolvimento' ? 'bg-violet-100 text-violet-700' : log.tipo === 'ajuste' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'}`}>
                                                    {log.tipo}
                                                  </span>
                                                  <span className="text-[8px] font-black text-slate-300 uppercase">{new Date(log.data_criacao).toLocaleDateString('pt-BR')}</span>
                                                </div>
                                                <p className="text-sm font-medium text-slate-700 leading-relaxed break-words">{log.descricao}</p>
                                                {log.pool_dados && log.pool_dados.length > 0 && (
                                                  <div className="flex flex-wrap gap-2 mt-3">
                                                    {log.pool_dados.map((at, i) => (
                                                      <a key={i} href={at.valor} target="_blank" rel="noopener noreferrer" className="block">
                                                        <img src={at.valor} alt="preview" className="w-20 h-20 object-cover rounded-lg border border-slate-100 hover:scale-105 transition-transform shadow-sm" />
                                                      </a>
                                                    ))}
                                                  </div>
                                                )}
                                              </div>
                                              <div className="flex gap-1 items-center opacity-0 group-hover:opacity-100 transition-opacity">
                                                <button
                                                  onClick={() => {
                                                    setEditingWorkItem(log);
                                                    setEditingWorkItemText(log.descricao);
                                                    setEditingWorkItemAttachments(log.pool_dados || []);
                                                  }}
                                                  className="p-2 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-lg transition-all"
                                                  title="Editar"
                                                >
                                                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                                </button>
                                                <button
                                                  onClick={() => {
                                                    if (confirmDeleteLogId === log.id) {
                                                      handleDeleteWorkItem(log.id);
                                                      setConfirmDeleteLogId(null);
                                                    } else {
                                                      setConfirmDeleteLogId(log.id);
                                                      setTimeout(() => setConfirmDeleteLogId(null), 3000);
                                                    }
                                                  }}
                                                  className={`p-2 rounded-lg transition-colors ${confirmDeleteLogId === log.id ? 'bg-rose-500 text-white shadow-md' : 'text-slate-400 hover:text-rose-600 hover:bg-rose-50'}`}
                                                  title="Excluir"
                                                >
                                                  {confirmDeleteLogId === log.id ? (
                                                    <svg className="w-4 h-4 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                  ) : (
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                  )}
                                                </button>
                                                <button
                                                  onClick={() => handleUpdateWorkItem(log.id, { concluido: true, data_conclusao: new Date().toISOString() })}
                                                  className="w-10 h-10 rounded-full border-2 border-slate-200 flex items-center justify-center text-slate-300 hover:border-emerald-500 hover:text-emerald-500 hover:bg-emerald-50 transition-all group/check ml-2"
                                                >
                                                  <svg className="w-5 h-5 opacity-0 group-hover/check:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                </button>
                                              </div>
                                            </div>
                                          </div>
                                        ))}
                                        {systemWorkItems.filter(w => !w.concluido).length === 0 && (
                                          <div className="text-center py-12 bg-slate-50/50 rounded-none md:rounded-3xl border-2 border-dashed border-slate-100">
                                            <p className="text-slate-300 font-black text-[10px] uppercase tracking-widest italic">Nenhum log ativo</p>
                                          </div>
                                        )}
                                      </div>
                                      {/* Concluídos */}
                                      {systemWorkItems.filter(w => w.concluido).length > 0 && (
                                        <div className="space-y-4 pt-8">
                                          <button
                                            onClick={() => setIsCompletedLogsOpen(!isCompletedLogsOpen)}
                                            className="w-full flex items-center justify-between group cursor-pointer"
                                          >
                                            <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest border-l-4 border-emerald-500 pl-3">Concluídos ({systemWorkItems.filter(w => w.concluido).length})</h5>
                                            <svg className={`w-4 h-4 text-slate-300 transition-transform ${isCompletedLogsOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" /></svg>
                                          </button>

                                          {isCompletedLogsOpen && (
                                            <div className="space-y-3 opacity-60 animate-in slide-in-from-top-2 duration-200">
                                              {systemWorkItems.filter(w => w.concluido).sort((a, b) => new Date(b.data_conclusao!).getTime() - new Date(a.data_conclusao!).getTime()).map(log => (
                                                <div key={log.id} className="bg-white border border-slate-100 rounded-none md:rounded-2xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 md:gap-4">
                                                  <div className="flex-1 flex items-center gap-4 w-full">
                                                    <div className="w-5 h-5 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
                                                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                    </div>
                                                    <p className="text-xs font-medium text-slate-500 line-clamp-1">{log.descricao}</p>
                                                    {log.pool_dados && log.pool_dados.length > 0 && (
                                                      <div className="flex flex-wrap gap-1 mt-1">
                                                        {log.pool_dados.map((at, i) => (
                                                          <a key={i} href={at.valor} target="_blank" rel="noopener noreferrer" className="block">
                                                            <img src={at.valor} alt="preview" className="w-8 h-8 object-cover rounded border border-slate-100 opacity-60 hover:opacity-100 transition-opacity" />
                                                          </a>
                                                        ))}
                                                      </div>
                                                    )}
                                                  </div>
                                                  <div className="flex gap-2 items-center">
                                                    <button
                                                      onClick={() => {
                                                        setEditingWorkItem(log);
                                                        setEditingWorkItemText(log.descricao);
                                                      }}
                                                      className="p-1.5 text-slate-300 hover:text-violet-600 rounded-lg transition-all"
                                                      title="Editar"
                                                    >
                                                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                                    </button>
                                                    <button
                                                      onClick={() => {
                                                        if (confirmDeleteLogId === log.id) {
                                                          handleDeleteWorkItem(log.id);
                                                          setConfirmDeleteLogId(null);
                                                        } else {
                                                          setConfirmDeleteLogId(log.id);
                                                          setTimeout(() => setConfirmDeleteLogId(null), 3000);
                                                        }
                                                      }}
                                                      className={`p-1.5 rounded-lg transition-colors ${confirmDeleteLogId === log.id ? 'bg-rose-500 text-white shadow-md' : 'text-slate-300 hover:text-rose-600'}`}
                                                      title="Excluir"
                                                    >
                                                      {confirmDeleteLogId === log.id ? (
                                                        <svg className="w-3.5 h-3.5 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                      ) : (
                                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                      )}
                                                    </button>
                                                    <button
                                                      onClick={() => handleUpdateWorkItem(log.id, { concluido: false })}
                                                      className="text-[9px] font-black text-slate-300 hover:text-violet-600 uppercase ml-2"
                                                    >
                                                      Reabrir
                                                    </button>
                                                  </div>
                                                </div>
                                              ))}
                                            </div>
                                          )}
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              </div>

                              {/* Modal de Edição de Recurso (Link) */}
                              {editingResource && (
                                <div className="fixed inset-0 z-[400] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 md:p-8 animate-in zoom-in-95 duration-300">
                                  <div className="bg-white w-full max-w-lg rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden">
                                    <div className="p-8 border-b border-slate-100 flex items-center justify-between">
                                      <h3 className="text-xl font-black text-slate-900 tracking-tight">Editar {editingResource.label}</h3>
                                      <button onClick={() => setEditingResource(null)} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                      </button>
                                    </div>
                                    <div className="p-8 space-y-6">
                                      <div className="space-y-2">
                                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">URL do Recurso</label>
                                        <input
                                          type="text"
                                          value={editingResource.value}
                                          onChange={(e) => setEditingResource({ ...editingResource, value: e.target.value })}
                                          placeholder="https://..."
                                          className="w-full bg-slate-50 border border-slate-200 rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-violet-500 transition-all"
                                        />
                                      </div>
                                      <div className="flex gap-4">
                                        <button
                                          onClick={() => setEditingResource(null)}
                                          className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-2xl transition-all"
                                        >
                                          Cancelar
                                        </button>
                                        <button
                                          onClick={() => {
                                            handleUpdateSistema(unit.id, { [editingResource.field]: editingResource.value });
                                            setEditingResource(null);
                                          }}
                                          className="flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all"
                                        >
                                          Salvar Link
                                        </button>
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              )}

                              {/* Modal de Logs Full-screen */}
                              {isLogsModalOpen && (
                                <div className={`fixed inset-0 z-[35] bg-white flex flex-col ${isSidebarRetracted ? 'md:pl-24' : 'md:pl-72'} pt-[60px] md:pt-[72px] animate-in fade-in duration-300`}>
                                  <div className="bg-white w-full h-full flex flex-col overflow-hidden shadow-2xl">
                                    <div className="p-6 md:p-10 border-b border-slate-100 flex items-center justify-between bg-white sticky top-0 z-10">
                                      <div className="flex items-center gap-4">
                                        <div className="p-3 bg-violet-100 text-violet-600 rounded-none md:rounded-2xl">
                                          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                        </div>
                                        <div>
                                          <h3 className="text-2xl font-black text-slate-900 tracking-tight">Registro de Atividades</h3>
                                          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">{systemName}</p>
                                        </div>
                                      </div>
                                      <button
                                        onClick={() => setIsLogsModalOpen(false)}
                                        className="p-3 bg-slate-100 text-slate-500 rounded-full hover:bg-slate-200 transition-all active:scale-95"
                                      >
                                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                      </button>
                                    </div>

                                    <div className="flex-1 overflow-y-auto p-6 md:p-12 space-y-12">
                                      <div className="space-y-6">
                                        <div className="flex items-center justify-between">
                                          <h5 className="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em] border-l-4 border-violet-500 pl-4">Logs em Aberto</h5>
                                          <span className="bg-violet-100 text-violet-600 text-[10px] font-black px-3 py-1 rounded-full uppercase tracking-widest">
                                            {systemWorkItems.filter(w => !w.concluido).length} Pendentes
                                          </span>
                                        </div>
                                        <div className="grid grid-cols-1 gap-6">
                                          {systemWorkItems.filter(w => !w.concluido).sort((a, b) => new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime()).map(log => (
                                            <div key={log.id} className="bg-slate-50 border border-slate-100 rounded-none md:rounded-[2.5rem] p-8 md:p-10 hover:shadow-xl hover:bg-white transition-all group relative overflow-hidden">
                                              {/* Decorative accent */}
                                              <div className="absolute top-0 left-0 w-1.5 h-full bg-violet-500 opacity-20 group-hover:opacity-100 transition-opacity"></div>

                                              <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-8">
                                                <div className="flex-1 min-w-0 space-y-4">
                                                  <div className="flex items-center flex-wrap gap-3">
                                                    <span className={`text-[9px] font-black px-3 py-1.5 rounded-full uppercase tracking-widest shadow-sm ${log.tipo === 'desenvolvimento' ? 'bg-violet-600 text-white' : log.tipo === 'ajuste' ? 'bg-amber-500 text-white' : 'bg-slate-200 text-slate-700'}`}>
                                                      {log.tipo}
                                                    </span>
                                                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">{new Date(log.data_criacao).toLocaleDateString('pt-BR')}</span>
                                                  </div>

                                                  <div className="space-y-4">
                                                    <p className="text-base md:text-xl font-bold text-slate-800 leading-[1.6] tracking-tight">{log.descricao}</p>

                                                    {log.pool_dados && log.pool_dados.length > 0 && (
                                                      <div className="flex flex-wrap gap-3 mt-6">
                                                        {log.pool_dados.map((at, i) => (
                                                          <a key={i} href={at.valor} target="_blank" rel="noopener noreferrer" className="block relative group/preview">
                                                            <div className="absolute inset-0 bg-violet-600/20 opacity-0 group-hover/preview:opacity-100 rounded-2xl transition-all z-10 flex items-center justify-center">
                                                              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
                                                            </div>
                                                            <img src={at.valor} alt="preview" className="w-24 h-24 object-cover rounded-2xl border-2 border-white shadow-md hover:scale-105 transition-transform" />
                                                          </a>
                                                        ))}
                                                      </div>
                                                    )}
                                                  </div>
                                                </div>

                                                <div className="flex items-center gap-3 shrink-0 self-end lg:self-start bg-white lg:bg-transparent p-2 lg:p-0 rounded-2xl shadow-sm lg:shadow-none border lg:border-none border-slate-100">
                                                  <button
                                                    onClick={() => {
                                                      setEditingWorkItem(log);
                                                      setEditingWorkItemText(log.descricao);
                                                      setEditingWorkItemAttachments(log.pool_dados || []);
                                                    }}
                                                    className="p-4 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-2xl transition-all"
                                                    title="Editar"
                                                  >
                                                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                                  </button>
                                                  <button
                                                    onClick={() => {
                                                      if (confirmDeleteLogId === log.id) {
                                                        handleDeleteWorkItem(log.id);
                                                        setConfirmDeleteLogId(null);
                                                      } else {
                                                        setConfirmDeleteLogId(log.id);
                                                        setTimeout(() => setConfirmDeleteLogId(null), 3000);
                                                      }
                                                    }}
                                                    className={`p-4 rounded-2xl transition-all ${confirmDeleteLogId === log.id ? 'bg-rose-500 text-white shadow-lg shadow-rose-200' : 'text-slate-400 hover:text-rose-600 hover:bg-rose-50'}`}
                                                    title="Excluir"
                                                  >
                                                    {confirmDeleteLogId === log.id ? (
                                                      <svg className="w-6 h-6 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                    ) : (
                                                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                    )}
                                                  </button>
                                                  <button
                                                    onClick={() => handleUpdateWorkItem(log.id, { concluido: true, data_conclusao: new Date().toISOString() })}
                                                    className="w-16 h-16 rounded-full bg-white border-2 border-slate-200 flex items-center justify-center text-slate-300 hover:border-emerald-500 hover:text-emerald-500 hover:bg-emerald-50 transition-all shadow-sm ml-2 group/check"
                                                  >
                                                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                  </button>
                                                </div>
                                              </div>
                                            </div>
                                          ))}
                                        </div>
                                      </div>

                                      {systemWorkItems.filter(w => w.concluido).length > 0 && (
                                        <div className="space-y-6">
                                          <button
                                            onClick={() => setIsModalCompletedLogsOpen(!isModalCompletedLogsOpen)}
                                            className="w-full flex items-center justify-between group cursor-pointer"
                                          >
                                            <h5 className="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em] border-l-4 border-emerald-500 pl-4">Concluídos ({systemWorkItems.filter(w => w.concluido).length})</h5>
                                            <svg className={`w-5 h-5 text-slate-300 transition-transform ${isModalCompletedLogsOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" /></svg>
                                          </button>

                                          {isModalCompletedLogsOpen && (
                                            <div className="grid grid-cols-1 gap-4 opacity-80 animate-in slide-in-from-top-4 duration-300">
                                              {systemWorkItems.filter(w => w.concluido).sort((a, b) => new Date(b.data_conclusao!).getTime() - new Date(a.data_conclusao!).getTime()).map(log => (
                                                <div key={log.id} className="bg-white border border-slate-100 rounded-none md:rounded-[2rem] p-8 flex flex-col md:flex-row md:items-center justify-between gap-6 hover:shadow-md transition-all">
                                                  <div className="flex-1 min-w-0 space-y-3">
                                                    <div className="flex items-center gap-3">
                                                      <span className="text-[10px] font-black text-emerald-500 bg-emerald-50 px-3 py-1 rounded-full uppercase tracking-widest">Concluído em {new Date(log.data_conclusao!).toLocaleDateString('pt-BR')}</span>
                                                    </div>
                                                    <p className="text-base font-bold text-slate-500 leading-relaxed line-clamp-2 hover:line-clamp-none transition-all">{log.descricao}</p>
                                                    {log.pool_dados && log.pool_dados.length > 0 && (
                                                      <div className="flex flex-wrap gap-2 mt-3">
                                                        {log.pool_dados.map((at, i) => (
                                                          <a key={i} href={at.valor} target="_blank" rel="noopener noreferrer" className="block relative group/preview">
                                                            <img src={at.valor} alt="preview" className="w-12 h-12 object-cover rounded-xl border border-slate-100 opacity-60 hover:opacity-100 transition-opacity shadow-sm" />
                                                          </a>
                                                        ))}
                                                      </div>
                                                    )}
                                                  </div>
                                                  <div className="flex gap-4 items-center shrink-0">
                                                    <button
                                                      onClick={() => {
                                                        setEditingWorkItem(log);
                                                        setEditingWorkItemText(log.descricao);
                                                      }}
                                                      className="p-3 text-slate-300 hover:text-violet-600 hover:bg-violet-50 rounded-xl transition-all"
                                                      title="Editar"
                                                    >
                                                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                                    </button>
                                                    <button
                                                      onClick={() => {
                                                        if (confirmDeleteLogId === log.id) {
                                                          handleDeleteWorkItem(log.id);
                                                          setConfirmDeleteLogId(null);
                                                        } else {
                                                          setConfirmDeleteLogId(log.id);
                                                          setTimeout(() => setConfirmDeleteLogId(null), 3000);
                                                        }
                                                      }}
                                                      className={`p-3 rounded-xl transition-all ${confirmDeleteLogId === log.id ? 'bg-rose-500 text-white shadow-lg' : 'text-slate-300 hover:text-rose-600 hover:bg-rose-50'}`}
                                                      title="Excluir"
                                                    >
                                                      {confirmDeleteLogId === log.id ? (
                                                        <svg className="w-5 h-5 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                      ) : (
                                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                      )}
                                                    </button>
                                                    <button
                                                      onClick={() => handleUpdateWorkItem(log.id, { concluido: false })}
                                                      className="px-6 py-3 bg-slate-900 text-white text-[10px] font-black uppercase tracking-widest rounded-xl hover:bg-violet-600 transition-all shadow-md active:scale-95 ml-2"
                                                    >
                                                      Reabrir
                                                    </button>
                                                  </div>
                                                </div>
                                              ))}
                                            </div>
                                          )}
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              )}
                              {/* Modal de Edição de Log */}
                              {editingWorkItem && (
                                <div className="fixed inset-0 z-[500] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 md:p-8 animate-in zoom-in-95 duration-300">
                                  <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden">
                                    <div className="p-8 border-b border-slate-100 flex items-center justify-between">
                                      <div className="flex items-center gap-4">
                                        <div className="p-3 bg-violet-100 text-violet-600 rounded-2xl">
                                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                        </div>
                                        <h3 className="text-xl font-black text-slate-900 tracking-tight">Editar Registro</h3>
                                      </div>
                                      <button onClick={() => setEditingWorkItem(null)} className="p-2 hover:bg-slate-100 rounded-full transition-colors text-slate-400">
                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                      </button>
                                    </div>
                                    <div className="p-8 space-y-6">
                                      <div className="space-y-4">
                                        <div className="space-y-2">
                                          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Descrição</label>
                                          <WysiwygEditor
                                            value={editingWorkItemText}
                                            onChange={setEditingWorkItemText}
                                            className="bg-slate-50 min-h-[120px]"
                                          />
                                        </div>

                                        <div className="space-y-2">
                                          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Anexos (Drive)</label>
                                          <div className="flex flex-wrap gap-2">
                                            {editingWorkItemAttachments.map((at, i) => (
                                              <div key={i} className="relative group/at">
                                                <img src={at.valor} alt="preview" className="w-20 h-20 object-cover rounded-xl border border-slate-200" />
                                                <button
                                                  onClick={() => setEditingWorkItemAttachments(prev => prev.filter((_, idx) => idx !== i))}
                                                  className="absolute -top-2 -right-2 bg-rose-500 text-white rounded-full p-1 opacity-0 group-hover/at:opacity-100 transition-all z-10 shadow-lg"
                                                >
                                                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                                </button>
                                              </div>
                                            ))}
                                            <label className={`w-20 h-20 border-2 border-dashed border-slate-200 rounded-xl flex items-center justify-center cursor-pointer hover:border-violet-400 hover:bg-violet-50 transition-all ${isUploading ? 'animate-pulse pointer-events-none' : ''}`}>
                                              <input
                                                type="file"
                                                accept="image/*"
                                                className="hidden"
                                                onChange={async (e) => {
                                                  const file = e.target.files?.[0];
                                                  if (file) {
                                                    const item = await handleFileUploadToDrive(file);
                                                    if (item) setEditingWorkItemAttachments(prev => [...prev, item]);
                                                  }
                                                }}
                                              />
                                              {isUploading ? (
                                                <div className="w-5 h-5 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
                                              ) : (
                                                <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                                              )}
                                            </label>
                                          </div>
                                        </div>
                                      </div>

                                      <div className="flex gap-4 pt-4">
                                        <button
                                          onClick={() => setEditingWorkItem(null)}
                                          className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-[1.5rem] transition-all"
                                        >
                                          Cancelar
                                        </button>
                                        <button
                                          onClick={() => {
                                            handleUpdateWorkItem(editingWorkItem.id, {
                                              descricao: editingWorkItemText,
                                              tipo: editingWorkItem.tipo,
                                              pool_dados: editingWorkItemAttachments
                                            });
                                            setEditingWorkItem(null);
                                            setEditingWorkItemAttachments([]);
                                          }}
                                          disabled={!editingWorkItemText.trim()}
                                          className="flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-[1.5rem] text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50"
                                        >
                                          Salvar Alterações
                                        </button>
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })()
                    )}
                  </div>



                ) : (
                  <div className="space-y-3 md:space-y-10">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 md:gap-6 bg-white p-3 md:p-8 rounded-none md:rounded-[2rem] border border-slate-200 shadow-xl">
                      <div className="hidden md:block">
                        <h3 className="text-4xl font-black text-slate-900 tracking-tighter">Gestão PGC</h3>
                        <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">{new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(new Date(currentYear, currentMonth))}</p>
                      </div>
                      <div className="flex items-center gap-3 md:gap-4">
                        {pgcSubView === 'plano' && (
                          <button
                            onClick={() => setIsImportPlanOpen(true)}
                            className="bg-slate-900 text-white px-4 md:px-6 py-2 md:py-3 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all flex items-center gap-2 md:gap-3"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                            Importar <span className="hidden md:inline">Planilha</span>
                          </button>
                        )}

                        <select
                          value={currentMonth}
                          onChange={(e) => setCurrentMonth(Number(e.target.value))}
                          className="flex-1 md:flex-none text-[10px] font-black uppercase bg-slate-100 px-4 py-2 rounded-lg md:rounded-xl border-none outline-none focus:ring-2 focus:ring-slate-900"
                        >
                          {['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'].map((m, i) => (
                            <option key={i} value={i}>{m}</option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div className="flex border-b border-slate-200 gap-4 md:gap-8">
                      <button
                        onClick={() => setPgcSubView('audit')}
                        className={`px-2 py-3 md:py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all border-b-4 ${pgcSubView === 'audit' ? 'border-slate-900 text-slate-900' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                      >
                        Resumo
                      </button>
                      <button
                        onClick={() => setPgcSubView('plano')}
                        className={`px-2 py-3 md:py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all border-b-4 ${pgcSubView === 'plano' ? 'border-slate-900 text-slate-900' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                      >
                        Plano
                      </button>
                    </div>

                    {pgcSubView === 'audit' && (
                      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 md:gap-6 h-[calc(100vh-180px)] pb-4">
                        <div className="lg:col-span-3 bg-white rounded-none md:rounded-[2rem] border border-slate-200 shadow-xl flex flex-col overflow-hidden h-full">
                          <div className="p-4 md:p-6 border-b border-slate-100 flex-shrink-0 bg-slate-50/50">
                            <div className="flex items-center justify-between">
                              <h4 className="text-sm font-black text-slate-900 tracking-tight">Pendentes</h4>
                              <span className="bg-slate-900 text-white text-[9px] font-black px-2 py-1 rounded-full">{pgcTasksAguardando.length}</span>
                            </div>
                            <p className="text-slate-400 text-[9px] font-black uppercase tracking-widest mt-1">Arraste p/ vincular</p>
                          </div>

                          <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
                            {pgcTasksAguardando.map(task => (
                              <PgcMiniTaskCard key={task.id} task={task} onClick={() => setSelectedTask(task)} />
                            ))}
                            {pgcTasksAguardando.length === 0 && (
                              <div className="py-10 text-center">
                                <p className="text-slate-300 font-black text-[9px] uppercase tracking-widest italic">Tudo limpo!</p>
                              </div>
                            )}
                          </div>
                        </div>

                        <div className="lg:col-span-9 bg-white rounded-none md:rounded-[2rem] border border-slate-200 overflow-hidden shadow-xl flex flex-col h-full">
                          <div className="flex-1 overflow-y-auto divide-y divide-slate-100 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
                            {(() => {
                              const currentPlan = planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`);

                              if (!currentPlan) return <div className="p-12 text-center h-full flex items-center justify-center"><p className="text-slate-300 font-black text-sm uppercase tracking-widest italic">Nenhum plano definido.</p></div>;

                              return currentPlan.itens.map((item, index) => {
                                const entregaEntity = pgcEntregas.find(e => e.entrega === item.entrega);
                                const entregaId = entregaEntity?.id;

                                const atividadesRelacionadas: AtividadeRealizada[] = entregaId ? atividadesPGC.filter(a => a.entrega_id === entregaId) : [];
                                const tarefasRelacionadas: Tarefa[] = entregaId ? pgcTasks.filter(t => t.entregas_relacionadas?.includes(entregaId)) : [];

                                return (
                                  <React.Fragment key={String(index)}>
                                    <PgcAuditRow
                                      item={item}
                                      entregaEntity={entregaEntity}
                                      atividadesRelacionadas={atividadesRelacionadas}
                                      tarefasRelacionadas={tarefasRelacionadas}
                                      onDrop={async (tarefaId) => {
                                        let targetId = entregaId;
                                        if (!targetId) {
                                          const newId = await handleCreateEntregaFromPlan(item);
                                          if (newId) targetId = newId;
                                        }
                                        if (targetId) handleLinkTarefa(tarefaId, targetId);
                                      }}
                                      onUnlinkTarefa={handleUnlinkTarefa}
                                      onSelectTask={setSelectedTask}
                                    />
                                  </React.Fragment>
                                );
                              });
                            })()}
                          </div>
                        </div>
                      </div>
                    )}

                    {pgcSubView === 'plano' && (
                      <div className="animate-in space-y-8">
                        <div className="bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl">
                          {/* Desktop Table */}
                          <table className="w-full text-left min-w-[800px] hidden md:table">
                            <thead className="bg-slate-50 border-b border-slate-200">
                              <tr>
                                <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Origem / Unidade</th>
                                <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Entrega Institucional</th>
                                <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Descrição</th>
                                <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-[200px]">% Carga Horária</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`)?.itens.map((item, i) => (
                                <tr key={i} className="hover:bg-slate-50 transition-colors">
                                  <td className="px-8 py-6">
                                    <div className="text-[10px] font-black text-slate-400 uppercase mb-1">{item.origem}</div>
                                    <div className="text-xs font-black text-slate-900">{item.unidade}</div>
                                  </td>
                                  <td className="px-8 py-6 text-sm font-black text-slate-900">{item.entrega}</td>
                                  <td className="px-8 py-6 text-xs font-medium text-slate-600 leading-relaxed max-w-xs">{item.descricao}</td>
                                  <td className="px-8 py-6">
                                    <div className="flex items-center gap-4">
                                      <div className="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden">
                                        <div className="h-full bg-indigo-500 rounded-full transition-all duration-1000" style={{ width: `${item.percentual}%` }}></div>
                                      </div>
                                      <span className="text-[10px] font-black text-slate-900 w-10">{item.percentual}%</span>
                                    </div>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>

                          {/* Mobile Card View */}
                          <div className="md:hidden divide-y divide-slate-100">
                            {planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`)?.itens.map((item, i) => (
                              <div key={i} className="p-6 space-y-4">
                                <div className="flex justify-between items-start gap-4">
                                  <div className="flex-1">
                                    <div className="text-[8px] font-black text-slate-400 uppercase mb-1">{item.origem} • {item.unidade}</div>
                                    <div className="text-sm font-black text-slate-900 leading-tight">{item.entrega}</div>
                                  </div>
                                  <div className="bg-indigo-50 text-indigo-600 px-2 py-1 rounded text-[10px] font-black">{item.percentual}%</div>
                                </div>
                                <p className="text-xs text-slate-500 leading-relaxed">{item.descricao}</p>
                                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                                  <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${item.percentual}%` }}></div>
                                </div>
                              </div>
                            ))}
                          </div>

                          {(!planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`)) && (
                            <div className="px-8 py-20 text-center">
                              <p className="text-slate-300 font-black text-sm uppercase tracking-widest italic">Nenhum plano de trabalho configurado para este período.</p>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </main>
            </div>
          </>
        </div>

        <ToastContainer toasts={toasts} removeToast={removeToast} />
        <HermesModal {...modalState} />

        {
          isCreateModalOpen && (
            <TaskCreateModal
              unidades={unidades}
              onSave={handleCreateTarefa}
              onClose={() => {
                setIsCreateModalOpen(false);
                setTaskInitialData(null);
              }}
              showAlert={showAlert}
              initialData={taskInitialData || undefined}
            />
          )
        }



        {
          selectedTask && (
            (taskModalMode === 'execute' || (taskModalMode === 'default' && selectedTask.categoria === 'CLC')) ? (
              <TaskExecutionView
                task={selectedTask}
                tarefas={tarefas}
                appSettings={appSettings}
                onSave={handleUpdateTarefa}
                onClose={() => setSelectedTask(null)}
                showToast={showToast}
                notifications={notifications}
                isSyncing={isSyncing}
                isNotificationCenterOpen={isNotificationCenterOpen}
                onOpenNotes={() => setIsQuickNoteModalOpen(true)}
                onOpenLog={() => setIsQuickLogModalOpen(true)}
                onOpenShopping={() => setIsShoppingAIModalOpen(true)}
                onOpenTranscription={() => setIsTranscriptionAIModalOpen(true)}
                onToggleNotifications={() => setIsNotificationCenterOpen(prev => !prev)}
                onSync={handleSync}
                onOpenSettings={() => setIsSettingsModalOpen(true)}
                onCloseNotifications={() => setIsNotificationCenterOpen(false)}
                onMarkAsRead={handleMarkNotificationRead}
                onDismiss={handleDismissNotification}
                onCreateAction={() => setIsCreateModalOpen(true)}
              />
            ) : (
              <TaskEditModal
                unidades={unidades}
                task={selectedTask}
                onSave={handleUpdateTarefa}
                onDelete={handleDeleteTarefa}
                onClose={() => setSelectedTask(null)}
                showAlert={showAlert}
                showConfirm={showConfirm}
                pgcEntregas={pgcEntregas}
              />
            )
          )
        }

        {
          isTerminalOpen && (
            <div className="fixed inset-0 z-[150] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-md animate-in fade-in duration-300">
              <div className="bg-[#0C0C0C] w-full max-w-2xl rounded-none md:rounded-[2rem] shadow-[0_0_100px_rgba(37,99,235,0.2)] border border-white/10 overflow-hidden flex flex-col h-[500px] animate-in zoom-in-95">
                <div className="p-6 bg-white/5 border-b border-white/5 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex gap-1.5">
                      <div className="w-3 h-3 rounded-full bg-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.5)]"></div>
                      <div className="w-3 h-3 rounded-full bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.5)]"></div>
                      <div className="w-3 h-3 rounded-full bg-emerald-500 shadow-[0_0_100px_rgba(16,185,129,0.5)]"></div>
                    </div>
                    <h3 className="text-[10px] font-black text-white/40 uppercase tracking-[0.3em] ml-2">Google Sync Console v2</h3>
                  </div>
                  <div className="flex items-center gap-4">
                    {isSyncing && (
                      <button
                        onClick={async () => {
                          await setDoc(doc(db, 'system', 'sync'), { status: 'idle', logs: [...(syncData?.logs || []), "--- INTERROMPIDO PELO USUÁRIO ---"] });
                          setIsSyncing(false);
                        }}
                        className="text-[9px] font-bold text-rose-500/60 hover:text-rose-400 bg-rose-500/10 border border-rose-500/20 px-3 py-1 rounded-full transition-all"
                      >
                        FORÇAR INTERRUPÇÃO
                      </button>
                    )}
                    <button onClick={() => setIsTerminalOpen(false)} className="text-white/40 hover:text-white transition-colors">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto p-6 font-mono text-[11px] space-y-2 selection:bg-blue-500/30">
                  <div className="text-blue-400 opacity-60"># hermes_cli.py --sync-mode automatic</div>
                  {syncData?.logs?.map((log: string, i: number) => (
                    <div key={i} className={`flex gap-3 ${log.includes('ERRO') ? 'text-rose-400' : log.includes('PUSH') ? 'text-blue-400' : log.includes('PULL') ? 'text-emerald-400' : 'text-slate-400'}`}>
                      <span className="opacity-30 shrink-0">[{i}]</span>
                      <span className="leading-relaxed">{log}</span>
                    </div>
                  ))}
                  {isSyncing && (
                    <div className="flex items-center gap-2 text-white/50 animate-pulse">
                      <span className="w-1.5 h-1.5 bg-blue-500 rounded-full"></span>
                      <span>Processando transações em tempo real...</span>
                    </div>
                  )}
                  {!isSyncing && syncData?.status === 'completed' && (
                    <div className="pt-4 border-t border-white/5 text-emerald-400 font-bold">
                      ✓ SINCROIZAÇÃO CONCLUÍDA COM SUCESSO.
                    </div>
                  )}
                  {syncData?.status === 'error' && (
                    <div className="pt-4 border-t border-white/5 text-rose-500 font-bold">
                      ⚠ FALHA NO PROCESSAMENTO: {syncData.error_message}
                    </div>
                  )}
                </div>

                <div className="p-4 bg-white/5 text-[9px] font-bold text-white/20 uppercase tracking-widest flex justify-between items-center">
                  <span>Core: Firebase Firestore + Google Tasks API</span>
                  <span>Encerrado: {syncData?.last_success ? formatDate(syncData.last_success.split('T')[0]) : '-'}</span>
                </div>
              </div>
            </div>
          )
        }

        {
          isSettingsModalOpen && (
            <SettingsModal
              settings={appSettings}
              unidades={unidades}
              initialTab={settingsTab}
              onSave={handleUpdateAppSettings}
              onClose={() => {
                setIsSettingsModalOpen(false);
                setSettingsTab('notifications');
              }}
              onAddUnidade={handleAddUnidade}
              onDeleteUnidade={handleDeleteUnidade}
              onUpdateUnidade={handleUpdateUnidade}
              onEmitNotification={emitNotification}
              showConfirm={showConfirm}
            />
          )
        }

        {
          isHabitsReminderOpen && (
            <DailyHabitsModal
              habits={healthDailyHabits.find(h => h.id === formatDateLocalISO(new Date())) || {
                id: formatDateLocalISO(new Date()),
                noSugar: false,
                noAlcohol: false,
                noSnacks: false,
                workout: false,
                eatUntil18: false,
                eatSlowly: false
              }}
              onUpdateHabits={handleUpdateHealthHabits}
              onClose={() => setIsHabitsReminderOpen(false)}
            />
          )
        }

        {
          isImportPlanOpen && (
            <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
              <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
                <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
                  <div>
                    <h3 className="text-2xl font-black text-slate-900 tracking-tight">Importar Plano Mensal</h3>
                    <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest">Cole o JSON do plano de trabalho abaixo</p>
                  </div>
                  <button onClick={() => setIsImportPlanOpen(false)} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
                    <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>

                <div className="p-8 space-y-6">
                  <div className="grid grid-cols-2 gap-6">
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Ano</label>
                      <input type="number" id="import-year" defaultValue={currentYear} className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900" />
                    </div>
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Mês</label>
                      <select id="import-month" defaultValue={currentMonth + 1} className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900">
                        {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(m => <option key={m} value={m}>{m}</option>)}
                      </select>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Dump JSON</label>
                    <textarea
                      id="import-json"
                      rows={10}
                      className="w-full bg-slate-900 text-blue-400 border-none rounded-none md:rounded-2xl px-6 py-4 text-[10px] font-mono focus:ring-2 focus:ring-blue-500 transition-all resize-none"
                      placeholder='[ { "entrega": "Exemplo", "percentual": 50 }, ... ]'
                    />
                  </div>
                </div>

                <div className="p-8 bg-slate-50 border-t border-slate-100 flex gap-4">
                  <button
                    onClick={() => setIsImportPlanOpen(false)}
                    className="flex-1 px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all"
                  >
                    Cancelar
                  </button>
                  <button
                    onClick={async () => {
                      try {
                        const year = (document.getElementById('import-year') as HTMLInputElement).value;
                        const month = (document.getElementById('import-month') as HTMLSelectElement).value.padStart(2, '0');
                        const rawText = (document.getElementById('import-json') as HTMLTextAreaElement).value;

                        let items: PlanoTrabalhoItem[] = [];

                        // Tenta detectar se é JSON ou o formato de texto/tabela
                        if (rawText.trim().startsWith('[') || rawText.trim().startsWith('{')) {
                          items = JSON.parse(rawText);
                        } else {
                          // Parser para o formato de tabela de texto
                          const lines = rawText.split('\n').map(l => l.trim()).filter(l => l !== '');
                          for (let i = 0; i < lines.length; i++) {
                            const line = lines[i];
                            if (line === 'Própria Unidade' || line === 'Outra Unidade') {
                              const item: Partial<PlanoTrabalhoItem> = { origem: line };
                              item.unidade = lines[++i] || '';
                              item.entrega = lines[++i] || '';
                              // Opcional: pular "Curtir"
                              if (lines[i + 1] === 'Curtir') i++;
                              const pctStr = lines[++i] || '0';
                              item.percentual = parseFloat(pctStr.replace('%', '')) || 0;
                              item.descricao = lines[++i] || '';
                              items.push(item as PlanoTrabalhoItem);
                            }
                          }
                        }

                        if (items.length === 0) throw new Error("Nenhum item identificado no texto colado.");

                        const docId = `${year}-${month}`;
                        await setDoc(doc(db, 'planos_trabalho', docId), {
                          mes_ano: docId,
                          itens: items,
                          data_atualizacao: new Date().toISOString()
                        });

                        setIsImportPlanOpen(false);
                        showAlert("Sucesso", `Sucesso! ${items.length} entregas importadas para o plano ${docId}.`);
                      } catch (err: any) {
                        showAlert("Erro", "Erro ao processar dados: " + err.message);
                      }
                    }}
                    className="flex-1 bg-blue-600 text-white px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all"
                  >
                    Processar e Gravar
                  </button>
                </div>
              </div>
            </div>
          )
        }

        {
          isSystemSelectorOpen && (
            <div className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
              <div className="bg-white w-full max-w-md rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95">
                <div className="p-8 border-b border-slate-100 flex items-center justify-between">
                  <h3 className="text-xl font-black text-slate-900">Selecionar Sistema</h3>
                  <button onClick={() => setIsSystemSelectorOpen(false)} className="p-2 hover:bg-slate-100 rounded-full">
                    <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>
                <div className="p-8 space-y-3 max-h-[400px] overflow-y-auto custom-scrollbar">
                  {unidades.filter(u => u.nome.startsWith('SISTEMA:')).map(sistema => (
                    <button
                      key={sistema.id}
                      onClick={() => handleFinalizeIdeaConversion(sistema.id)}
                      className="w-full text-left p-4 rounded-none md:rounded-2xl border-2 border-slate-100 hover:border-violet-500 hover:bg-violet-50 transition-all flex items-center gap-3 group"
                    >
                      <div className="w-10 h-10 bg-slate-100 group-hover:bg-violet-500 group-hover:text-white rounded-lg md:rounded-xl flex items-center justify-center transition-colors">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                      </div>
                      <span className="font-bold text-slate-700 group-hover:text-violet-700">{sistema.nome.replace('SISTEMA:', '').trim()}</span>
                    </button>
                  ))}
                  {unidades.filter(u => u.nome.startsWith('SISTEMA:')).length === 0 && (
                    <p className="text-center text-slate-400 py-8 italic text-sm">Nenhum sistema cadastrado.</p>
                  )}
                </div>
              </div>
            </div>
          )
        }

        {
          isQuickNoteModalOpen && (
            <QuickNoteModal
              isOpen={isQuickNoteModalOpen}
              onClose={() => setIsQuickNoteModalOpen(false)}
              onAddIdea={handleAddTextIdea}
              showAlert={showAlert}
            />
          )
        }

        {
          isQuickLogModalOpen && (
            <QuickLogModal
              isOpen={isQuickLogModalOpen}
              onClose={() => setIsQuickLogModalOpen(false)}
              onAddLog={handleAddQuickLog}
              unidades={unidades}
            />
          )
        }

        {
          isShoppingAIModalOpen && (
            <ShoppingAIModal
              isOpen={isShoppingAIModalOpen}
              onClose={() => setIsShoppingAIModalOpen(false)}
              catalogItems={shoppingItems}
              onConfirmItems={handleShoppingAIConfirm}
              onViewList={() => {
                setActiveFerramenta('shopping');
                setIsShoppingAIModalOpen(false);
              }}
            />
          )
        }

        {
          isTranscriptionAIModalOpen && (
            <TranscriptionAIModal
              isOpen={isTranscriptionAIModalOpen}
              onClose={() => setIsTranscriptionAIModalOpen(false)}
              showToast={showToast}
            />
          )
        }
      </div>
    </>
  );
};

const container = document.getElementById('root');
if (container) {
  const root = createRoot(container);
  root.render(<App />);
}
