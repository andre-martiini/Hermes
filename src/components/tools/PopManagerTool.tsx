import React, { useState, useEffect } from 'react';
import { collection, addDoc, getDocs, doc, updateDoc, deleteDoc } from 'firebase/firestore';
import { db } from '@/firebase';

interface Pop {
  id: string;
  titulo: string;
  gatilhos: string[];
  instrucao_sistema: string;
}

export const PopManagerTool: React.FC = () => {
  const [pops, setPops] = useState<Pop[]>([]);
  const [loading, setLoading] = useState(true);

  // Form State
  const [editingId, setEditingId] = useState<string | null>(null);
  const [titulo, setTitulo] = useState('');
  const [gatilhos, setGatilhos] = useState('');
  const [instrucao, setInstrucao] = useState('');

  const fetchPops = async () => {
    setLoading(true);
    try {
      const querySnapshot = await getDocs(collection(db, 'pops_diretrizes'));
      const popData: Pop[] = [];
      querySnapshot.forEach((doc) => {
        popData.push({ id: doc.id, ...doc.data() } as Pop);
      });
      setPops(popData);
    } catch (error) {
      console.error("Erro ao buscar POPs:", error);
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
      fetchPops();
    } catch (error) {
      console.error("Erro ao salvar POP:", error);
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
      await deleteDoc(doc(db, 'pops_diretrizes', id));
      fetchPops();
    } catch (error) {
      console.error("Erro ao excluir POP:", error);
    }
  };

  const resetForm = () => {
    setEditingId(null);
    setTitulo('');
    setGatilhos('');
    setInstrucao('');
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-3xl overflow-hidden shadow-sm border border-slate-200">
      <div className="p-6 md:p-8 bg-slate-50 border-b border-slate-200 shrink-0">
        <h2 className="text-2xl font-black text-slate-800 uppercase tracking-tight flex items-center gap-3">
          <svg className="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          Gestor de POPs
        </h2>
        <p className="text-slate-500 mt-2 font-medium">Gerencie os Procedimentos Operacionais Padrão (POPs) que orientam o Hermes Copiloto.</p>
      </div>

      <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-8">

        {/* Formulário de Criação/Edição */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
          <h3 className="text-lg font-bold text-slate-800 mb-4">{editingId ? 'Editar POP' : 'Novo POP'}</h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">Título</label>
              <input
                type="text"
                placeholder="Ex: Formatação de Relatório Financeiro"
                value={titulo}
                onChange={(e) => setTitulo(e.target.value)}
                required
                className="w-full p-3 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">Gatilhos (separados por vírgula)</label>
              <input
                type="text"
                placeholder="Ex: relatório financeiro, formatar gastos"
                value={gatilhos}
                onChange={(e) => setGatilhos(e.target.value)}
                required
                className="w-full p-3 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">Instrução de Sistema</label>
              <textarea
                placeholder="Descreva a regra exata e o formato que o LLM deve seguir..."
                value={instrucao}
                onChange={(e) => setInstrucao(e.target.value)}
                required
                className="w-full p-3 border border-slate-300 rounded-xl h-32 resize-none focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>

            <div className="flex gap-3 pt-2">
              <button
                type="submit"
                className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-6 rounded-xl transition-colors"
              >
                {editingId ? 'Atualizar POP' : 'Salvar POP'}
              </button>
              {editingId && (
                <button
                  type="button"
                  onClick={resetForm}
                  className="bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold py-3 px-6 rounded-xl transition-colors"
                >
                  Cancelar
                </button>
              )}
            </div>
          </form>
        </div>

        {/* Lista de POPs */}
        <div>
          <h3 className="text-lg font-bold text-slate-800 mb-4 border-b border-slate-100 pb-2">POPs Cadastrados</h3>
          {loading ? (
             <div className="text-center py-8 text-slate-400 font-medium animate-pulse">Carregando POPs...</div>
          ) : pops.length === 0 ? (
            <div className="text-center py-8 bg-slate-50 rounded-2xl border border-dashed border-slate-300">
              <p className="text-slate-500 font-medium">Nenhum POP cadastrado.</p>
            </div>
          ) : (
            <div className="grid gap-4">
              {pops.map((pop) => (
                <div key={pop.id} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow group">
                  <div className="flex justify-between items-start mb-3">
                    <h4 className="font-bold text-lg text-slate-800">{pop.titulo}</h4>
                    <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => handleEdit(pop)} className="text-blue-500 hover:text-blue-700 p-1">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                      </button>
                      <button onClick={() => handleDelete(pop.id)} className="text-red-500 hover:text-red-700 p-1">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                      </button>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 mb-3">
                    {pop.gatilhos.map((g, i) => (
                      <span key={i} className="bg-blue-50 text-blue-700 text-xs font-bold px-2 py-1 rounded-md">
                        {g}
                      </span>
                    ))}
                  </div>
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                    <p className="text-slate-600 text-sm font-mono whitespace-pre-wrap line-clamp-3 group-hover:line-clamp-none transition-all">
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
