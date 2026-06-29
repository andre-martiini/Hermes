import React, { useState, useEffect } from 'react';
import { db, auth } from '@/firebase';
import {
  collection,
  addDoc,
  deleteDoc,
  updateDoc,
  doc,
  query,
  where,
  onSnapshot,
} from 'firebase/firestore';
import { PaginaMonitorada } from '@/types';

interface MonitorPaginasToolProps {
  onBack: () => void;
  isDark?: boolean;
}

const isValidUrl = (value: string): boolean => {
  try {
    const u = new URL(value.trim());
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch {
    return false;
  }
};

const formatarData = (iso?: string): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
};

export const MonitorPaginasTool: React.FC<MonitorPaginasToolProps> = ({ onBack, isDark = false }) => {
  const [paginas, setPaginas] = useState<PaginaMonitorada[]>([]);
  const [url, setUrl] = useState('');
  const [apelido, setApelido] = useState('');
  const [objetivo, setObjetivo] = useState('');
  const [seletorCss, setSeletorCss] = useState('');
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  const [editId, setEditId] = useState<string | null>(null);
  const [editUrl, setEditUrl] = useState('');
  const [editApelido, setEditApelido] = useState('');
  const [editObjetivo, setEditObjetivo] = useState('');
  const [editSeletor, setEditSeletor] = useState('');
  const [editErro, setEditErro] = useState<string | null>(null);

  useEffect(() => {
    const uid = auth.currentUser?.uid;
    if (!uid) return;
    const q = query(collection(db, 'paginas_monitoradas'), where('userId', '==', uid));
    const unsub = onSnapshot(q, (snap) => {
      const items = snap.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<PaginaMonitorada, 'id'>) }));
      items.sort((a, b) => (b.criado_em || '').localeCompare(a.criado_em || ''));
      setPaginas(items);
    });
    return () => unsub();
  }, []);

  const handleAdd = async () => {
    setErro(null);
    const uid = auth.currentUser?.uid;
    if (!uid) {
      setErro('Você precisa estar autenticado.');
      return;
    }
    if (!isValidUrl(url)) {
      setErro('Informe uma URL válida (http/https).');
      return;
    }
    if (!objetivo.trim()) {
      setErro('Descreva o objetivo — é o que define quando você será avisado.');
      return;
    }
    setSalvando(true);
    try {
      await addDoc(collection(db, 'paginas_monitoradas'), {
        url: url.trim(),
        apelido: apelido.trim() || new URL(url.trim()).hostname,
        objetivo: objetivo.trim(),
        seletor_css: seletorCss.trim() || null,
        hash_atual: null,
        texto_atual: null,
        ultima_verificacao: null,
        ultima_mudanca: null,
        ultima_analise: null,
        ativo: true,
        userId: uid,
        criado_em: new Date().toISOString(),
      });
      setUrl('');
      setApelido('');
      setObjetivo('');
      setSeletorCss('');
    } catch (e: any) {
      setErro(`Falha ao salvar: ${e?.message || e}`);
    } finally {
      setSalvando(false);
    }
  };

  const toggleAtivo = async (p: PaginaMonitorada) => {
    await updateDoc(doc(db, 'paginas_monitoradas', p.id), { ativo: !p.ativo });
  };

  const remover = async (p: PaginaMonitorada) => {
    await deleteDoc(doc(db, 'paginas_monitoradas', p.id));
  };

  const iniciarEdicao = (p: PaginaMonitorada) => {
    setEditId(p.id);
    setEditUrl(p.url);
    setEditApelido(p.apelido);
    setEditObjetivo(p.objetivo);
    setEditSeletor(p.seletor_css || '');
    setEditErro(null);
  };

  const cancelarEdicao = () => {
    setEditId(null);
    setEditErro(null);
  };

  const salvarEdicao = async (p: PaginaMonitorada) => {
    setEditErro(null);
    if (!isValidUrl(editUrl)) {
      setEditErro('Informe uma URL válida (http/https).');
      return;
    }
    if (!editObjetivo.trim()) {
      setEditErro('O objetivo não pode ficar vazio.');
      return;
    }
    const novaUrl = editUrl.trim();
    const novoSeletor = editSeletor.trim() || null;
    const update: Record<string, any> = {
      url: novaUrl,
      apelido: editApelido.trim() || new URL(novaUrl).hostname,
      objetivo: editObjetivo.trim(),
      seletor_css: novoSeletor,
    };
    // Mudar URL ou seletor invalida o baseline — reseta para recapturar na próxima verificação.
    if (novaUrl !== p.url || novoSeletor !== (p.seletor_css || null)) {
      update.hash_atual = null;
      update.texto_atual = null;
      update.ultima_mudanca = null;
      update.ultima_analise = null;
    }
    await updateDoc(doc(db, 'paginas_monitoradas', p.id), update);
    setEditId(null);
  };

  const inputClass = `w-full font-mono text-sm px-4 py-3 rounded-none border outline-none transition-all ${
    isDark
      ? 'bg-slate-900 border-slate-700 text-slate-100 focus:border-emerald-500 placeholder-slate-600'
      : 'bg-white border-slate-200 text-slate-800 focus:border-emerald-500 placeholder-slate-400'
  }`;

  return (
    <div className={`flex flex-col h-full ${isDark ? 'bg-slate-950 text-slate-100' : 'bg-slate-50 text-slate-800'}`}>
      {/* Header */}
      <div className={`flex items-center justify-between px-6 py-4 border-b shrink-0 ${isDark ? 'border-slate-800 bg-slate-900' : 'border-slate-200 bg-white'}`}>
        <div className="flex items-center gap-3">
          <button onClick={onBack} className={`p-2 rounded-none transition-colors ${isDark ? 'hover:bg-slate-800 text-slate-400 hover:text-slate-100' : 'hover:bg-slate-100 text-slate-500 hover:text-slate-950'}`}>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div>
            <p className="text-[10px] font-mono font-bold text-emerald-500 uppercase tracking-wider leading-none mb-1">MONITORAMENTO WEB</p>
            <h3 className="text-lg font-mono font-bold uppercase tracking-tight">Monitor de Páginas</h3>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Form */}
        <div className={`p-6 rounded-none border ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
          <h4 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-400 mb-4">Adicionar Página</h4>
          <div className="space-y-3">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://exemplo.gov.br/pagina-a-acompanhar"
              className={inputClass}
            />
            <input
              type="text"
              value={apelido}
              onChange={(e) => setApelido(e.target.value)}
              placeholder="Apelido (opcional) — ex.: Compras AVN"
              className={inputClass}
            />
            <textarea
              value={objetivo}
              onChange={(e) => setObjetivo(e.target.value)}
              placeholder="Objetivo — ex.: verificar se as contratações do almoxarifado virtual já foram realizadas"
              rows={2}
              className={`${inputClass} resize-none`}
            />
            <input
              type="text"
              value={seletorCss}
              onChange={(e) => setSeletorCss(e.target.value)}
              placeholder="Seletor CSS (opcional) — restringe a região monitorada, ex.: #content"
              className={inputClass}
            />
            {erro && (
              <div className="p-3 border border-rose-500/20 bg-rose-500/5 text-rose-500 text-xs font-mono font-bold">
                {erro}
              </div>
            )}
            <button
              onClick={handleAdd}
              disabled={salvando}
              className="h-[46px] w-full sm:w-auto px-6 rounded-none font-mono text-xs font-bold uppercase tracking-wider transition-all inline-flex items-center justify-center gap-2 text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50"
            >
              {salvando ? 'Salvando...' : 'Monitorar'}
            </button>
          </div>
        </div>

        {/* List */}
        {paginas.length === 0 ? (
          <div className={`py-20 text-center border-2 border-dashed rounded-none ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
            <p className="text-slate-400 font-mono text-[10px] font-bold uppercase tracking-wider">Nenhuma Página Monitorada</p>
            <p className="text-slate-500 text-xs mt-1">Adicione uma URL e um objetivo. A sincronização avisará você no Telegram quando o objetivo avançar.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {paginas.map((p) => (
              <div key={p.id} className={`p-4 rounded-none border ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'} ${!p.ativo ? 'opacity-50' : ''}`}>
                {editId === p.id ? (
                  <div className="space-y-3">
                    <p className="text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-500">Editando página</p>
                    <input
                      type="url"
                      value={editUrl}
                      onChange={(e) => setEditUrl(e.target.value)}
                      placeholder="URL"
                      className={inputClass}
                    />
                    <input
                      type="text"
                      value={editApelido}
                      onChange={(e) => setEditApelido(e.target.value)}
                      placeholder="Apelido"
                      className={inputClass}
                    />
                    <textarea
                      value={editObjetivo}
                      onChange={(e) => setEditObjetivo(e.target.value)}
                      placeholder="Objetivo"
                      rows={2}
                      className={`${inputClass} resize-none`}
                    />
                    <input
                      type="text"
                      value={editSeletor}
                      onChange={(e) => setEditSeletor(e.target.value)}
                      placeholder="Seletor CSS (opcional)"
                      className={inputClass}
                    />
                    {(editUrl.trim() !== p.url || (editSeletor.trim() || null) !== (p.seletor_css || null)) && (
                      <p className="text-[10px] font-mono text-amber-500">
                        Alterar URL ou seletor reinicia o baseline — a próxima verificação recaptura sem alertar.
                      </p>
                    )}
                    {editErro && (
                      <div className="p-3 border border-rose-500/20 bg-rose-500/5 text-rose-500 text-xs font-mono font-bold">
                        {editErro}
                      </div>
                    )}
                    <div className="flex gap-2">
                      <button
                        onClick={() => salvarEdicao(p)}
                        className="px-4 py-2 font-mono text-[9px] font-bold uppercase tracking-wider text-white bg-emerald-600 hover:bg-emerald-700 transition-all"
                      >
                        Salvar
                      </button>
                      <button
                        onClick={cancelarEdicao}
                        className="px-4 py-2 font-mono text-[9px] font-bold uppercase tracking-wider border border-slate-400/40 text-slate-400 hover:bg-slate-400/10 transition-all"
                      >
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-none ${p.ativo ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                        <span className="font-mono text-sm font-bold tracking-tight truncate">{p.apelido}</span>
                      </div>
                      <a href={p.url} target="_blank" rel="noreferrer" className="block text-[11px] text-emerald-500 hover:underline font-mono truncate mt-1">
                        {p.url}
                      </a>
                      <p className="text-xs text-slate-400 mt-2 line-clamp-2">
                        <span className="font-bold uppercase tracking-wider text-[9px] text-slate-500">Objetivo: </span>
                        {p.objetivo}
                      </p>
                      {p.ultima_analise && (
                        <p className={`text-xs mt-2 p-2 rounded-none ${isDark ? 'bg-slate-800/60' : 'bg-slate-100'}`}>
                          <span className="font-bold uppercase tracking-wider text-[9px] text-emerald-500">Última análise: </span>
                          {p.ultima_analise}
                        </p>
                      )}
                      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[10px] font-mono text-slate-500">
                        <span>Verificada: {formatarData(p.ultima_verificacao)}</span>
                        <span>Última mudança: {formatarData(p.ultima_mudanca)}</span>
                      </div>
                    </div>
                    <div className="flex flex-col gap-2 shrink-0">
                      <button
                        onClick={() => iniciarEdicao(p)}
                        className="px-3 py-1.5 font-mono text-[9px] font-bold uppercase tracking-wider border border-slate-400/40 text-slate-400 hover:bg-slate-400/10 transition-all"
                      >
                        Editar
                      </button>
                      <button
                        onClick={() => toggleAtivo(p)}
                        className={`px-3 py-1.5 font-mono text-[9px] font-bold uppercase tracking-wider border transition-all ${
                          p.ativo
                            ? 'border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10'
                            : 'border-slate-400/40 text-slate-400 hover:bg-slate-400/10'
                        }`}
                      >
                        {p.ativo ? 'Ativo' : 'Pausado'}
                      </button>
                      <button
                        onClick={() => remover(p)}
                        className="px-3 py-1.5 font-mono text-[9px] font-bold uppercase tracking-wider border border-rose-500/40 text-rose-500 hover:bg-rose-500/10 transition-all"
                      >
                        Remover
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
