import React, { useState, useEffect } from 'react';
import { collection, addDoc, getDocs, doc, updateDoc, deleteDoc } from 'firebase/firestore';
import { db } from '@/firebase';

interface Pop {
  id: string;
  titulo: string;
  gatilhos: string[];
  instrucao_sistema: string;
}

interface PopManagerToolProps {
  onBack?: () => void;
  initialSearch?: string;
  isEmbedded?: boolean;
  isDark?: boolean;
}

export const PopManagerTool: React.FC<PopManagerToolProps> = ({ onBack, initialSearch, isEmbedded, isDark }) => {
  const [pops, setPops] = useState<Pop[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [searchTerm, setSearchTerm] = useState(initialSearch || '');


  // Form State
  const [editingId, setEditingId] = useState<string | null>(null);
  const [titulo, setTitulo] = useState('');
  const [gatilhos, setGatilhos] = useState('');
  const [instrucao, setInstrucao] = useState('');

  const getErrorMessage = (error: unknown) => {
    const code = typeof error === 'object' && error !== null && 'code' in error
      ? String((error as { code?: unknown }).code)
      : '';

    if (code.includes('network') || code.includes('unavailable') || code.includes('failed-precondition')) {
      return 'Nao foi possivel conectar ao Firebase. O navegador perdeu acesso seguro ao backend.';
    }

    if (code.includes('permission-denied')) {
      return 'Seu usuario nao tem permissao para salvar POPs.';
    }

    return 'Falha ao acessar os POPs. Verifique a conexao com o Firebase e tente novamente.';
  };

  const fetchPops = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const querySnapshot = await getDocs(collection(db, 'pops_diretrizes'));
      const popData: Pop[] = [];
      querySnapshot.forEach((doc) => {
        popData.push({ id: doc.id, ...doc.data() } as Pop);
      });
      setPops(popData);
    } catch (error) {
      console.error("Erro ao buscar POPs:", error);
      setErrorMessage(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPops();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const arrayGatilhos = gatilhos.split(',').map(g => g.trim().toLowerCase()).filter(g => g);

    try {
      setSaving(true);
      setErrorMessage(null);
      if (editingId) {
        const popRef = doc(db, 'pops_diretrizes', editingId);
        await updateDoc(popRef, {
          titulo,
          gatilhos: arrayGatilhos,
          instrucao_sistema: instrucao,
        });
      } else {
        await addDoc(collection(db, 'pops_diretrizes'), {
          titulo,
          gatilhos: arrayGatilhos,
          instrucao_sistema: instrucao,
        });
      }
      resetForm();
      await fetchPops();
    } catch (error) {
      console.error("Erro ao salvar POP:", error);
      setErrorMessage(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (pop: Pop) => {
    setEditingId(pop.id);
    setTitulo(pop.titulo);
    setGatilhos(pop.gatilhos.join(', '));
    setInstrucao(pop.instrucao_sistema);
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm("Tem certeza que deseja excluir este POP?")) return;
    try {
      setErrorMessage(null);
      await deleteDoc(doc(db, 'pops_diretrizes', id));
      await fetchPops();
    } catch (error) {
      console.error("Erro ao excluir POP:", error);
      setErrorMessage(getErrorMessage(error));
    }
  };

  const resetForm = () => {
    setEditingId(null);
    setTitulo('');
    setGatilhos('');
    setInstrucao('');
  };

  return (
    <div className={`flex flex-col h-full rounded-none-3xl overflow-hidden shadow-none border ${isDark ? 'bg-slate-900 border-slate-700/50' : 'bg-white border-slate-200'}`}>
      <div className={`p-6 md:p-8 border-b shrink-0 ${isDark ? 'bg-slate-800/50 border-slate-700/50' : 'bg-slate-50 border-slate-200'}`}>
        <div className="flex items-center gap-4 mb-4">
          {onBack && !isEmbedded && (
            <button onClick={onBack} className={`p-2 rounded-none-none transition-colors ${isDark ? 'text-slate-400 hover:text-white hover:bg-slate-700' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'}`}>
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
            </button>
          )}
          <h2 className={`text-2xl font-bold uppercase tracking-tight flex items-center gap-3 ${isDark ? 'text-white' : 'text-slate-800'}`}>
            <svg className={`w-8 h-8 ${isDark ? 'text-cyan-400' : 'text-blue-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
            Gestor de POPs
          </h2>
        </div>
        <p className={`mt-2 font-medium ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Gerencie os Procedimentos Operacionais Padrão (POPs) que orientam o Hermes Copiloto.</p>
      </div>

      <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-8">
        {errorMessage && (
          <div className={`rounded-none-none border px-4 py-3 text-sm font-medium ${isDark ? 'border-red-900/50 bg-red-900/20 text-red-400' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
            {errorMessage}
          </div>
        )}

        {/* Formulário de Criação/Edição */}
        <div className={`p-6 rounded-none-none border shadow-none ${isDark ? 'bg-slate-800/50 border-slate-700/50' : 'bg-white border-slate-200'}`}>
          <h3 className={`text-lg font-bold mb-4 ${isDark ? 'text-white' : 'text-slate-800'}`}>{editingId ? 'Editar POP' : 'Novo POP'}</h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className={`block text-sm font-semibold mb-1 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>Título</label>
              <input
                type="text"
                placeholder="Ex: Formatação de Relatório Financeiro"
                value={titulo}
                onChange={(e) => setTitulo(e.target.value)}
                required
                className={`w-full p-3 border rounded-none-none focus:ring-1 outline-none transition-colors ${isDark ? 'bg-slate-900/50 border-slate-700 text-white focus:ring-cyan-500/50 placeholder-slate-500' : 'bg-white border-slate-300 text-slate-900 focus:ring-blue-500 placeholder-slate-400'}`}
              />
            </div>
            <div>
              <label className={`block text-sm font-semibold mb-1 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>Gatilhos (separados por vírgula)</label>
              <input
                type="text"
                placeholder="Ex: relatório financeiro, formatar gastos"
                value={gatilhos}
                onChange={(e) => setGatilhos(e.target.value)}
                required
                className={`w-full p-3 border rounded-none-none focus:ring-1 outline-none transition-colors ${isDark ? 'bg-slate-900/50 border-slate-700 text-white focus:ring-cyan-500/50 placeholder-slate-500' : 'bg-white border-slate-300 text-slate-900 focus:ring-blue-500 placeholder-slate-400'}`}
              />
            </div>
            <div>
              <label className={`block text-sm font-semibold mb-1 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>Instrução de Sistema</label>
              <textarea
                placeholder="Descreva a regra exata e o formato que o LLM deve seguir..."
                value={instrucao}
                onChange={(e) => setInstrucao(e.target.value)}
                required
                className={`w-full p-3 border rounded-none-none h-32 resize-none focus:ring-1 outline-none transition-colors ${isDark ? 'bg-slate-900/50 border-slate-700 text-white focus:ring-cyan-500/50 placeholder-slate-500' : 'bg-white border-slate-300 text-slate-900 focus:ring-blue-500 placeholder-slate-400'}`}
              />
            </div>

            <div className="flex gap-3 pt-2">
              <button
                type="submit"
                disabled={saving}
                className={`font-bold py-3 px-6 rounded-none-none transition-colors ${isDark ? 'bg-cyan-600 hover:bg-cyan-500 text-white' : 'bg-blue-600 hover:bg-blue-700 text-white'}`}
              >
                {saving ? 'Salvando...' : editingId ? 'Atualizar POP' : 'Salvar POP'}
              </button>
              {editingId && (
                <button
                  type="button"
                  onClick={resetForm}
                  className={`font-bold py-3 px-6 rounded-none-none transition-colors ${isDark ? 'bg-slate-700 hover:bg-slate-600 text-white' : 'bg-slate-200 hover:bg-slate-300 text-slate-700'}`}
                >
                  Cancelar
                </button>
              )}
            </div>
          </form>
        </div>

        {/* Lista de POPs */}
        <div>
          <h3 className={`text-lg font-bold mb-4 border-b pb-2 ${isDark ? 'text-white border-slate-700/50' : 'text-slate-800 border-slate-200'}`}>POPs Cadastrados</h3>
          {loading ? (
             <div className={`text-center py-8 font-medium animate-pulse ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Carregando POPs...</div>
          ) : pops.length === 0 ? (
            <div className={`text-center py-8 rounded-none-none border border-dashed ${isDark ? 'bg-slate-800/30 border-slate-700' : 'bg-slate-50 border-slate-300'}`}>
              <p className={`font-medium ${isDark ? 'text-slate-500' : 'text-slate-500'}`}>Nenhum POP cadastrado.</p>
            </div>
          ) : (
            <div className="grid gap-4">
              {pops.map((pop) => (
                <div key={pop.id} className={`border rounded-none-none p-5 shadow-none hover:shadow-none transition-shadow group ${isDark ? 'bg-slate-800/50 border-slate-700/50' : 'bg-white border-slate-200'}`}>
                  <div className="flex justify-between items-start mb-3">
                    <h4 className={`font-bold text-lg ${isDark ? 'text-white' : 'text-slate-800'}`}>{pop.titulo}</h4>
                    <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => handleEdit(pop)} className={`p-1 transition-colors ${isDark ? 'text-cyan-400 hover:text-cyan-300' : 'text-blue-500 hover:text-blue-700'}`}>
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                      </button>
                      <button onClick={() => handleDelete(pop.id)} className={`p-1 transition-colors ${isDark ? 'text-red-400 hover:text-red-300' : 'text-red-500 hover:text-red-700'}`}>
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                      </button>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 mb-3">
                    {pop.gatilhos.map((g, i) => (
                      <span key={i} className={`text-xs font-bold px-2 py-1 rounded-none-none ${isDark ? 'bg-cyan-900/30 text-cyan-400' : 'bg-blue-50 text-blue-700'}`}>
                        {g}
                      </span>
                    ))}
                  </div>
                  <div className={`p-3 rounded-none-none border ${isDark ? 'bg-slate-900/50 border-slate-700/50' : 'bg-slate-50 border-slate-200'}`}>
                    <p className={`text-sm font-mono whitespace-pre-wrap line-clamp-3 group-hover:line-clamp-none transition-all ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                      {pop.instrucao_sistema}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
};
