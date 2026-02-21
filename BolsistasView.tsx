// BolsistasView.tsx
import React, { useState, useEffect } from 'react';
import { collection, addDoc, onSnapshot, query } from 'firebase/firestore';
import { db } from './firebase'; // Ajuste o caminho da importação
import { Bolsista, StatusConvocacao } from './types';

interface BolsistasViewProps {
  projetoId: string; // ID do projeto (ex: SIGEX)
}

export const BolsistasView: React.FC<BolsistasViewProps> = ({ projetoId }) => {
  const [bolsistas, setBolsistas] = useState<Bolsista[]>([]);
  const [formData, setFormData] = useState<Partial<Bolsista>>({
    status: 'Em regularização',
  });

  // Cálculo automático do interstício
  const calcularIntersticio = (inicio: string, fim: string): number => {
    if (!inicio || !fim) return 0;
    const d1 = new Date(inicio);
    const d2 = new Date(fim);
    const meses = (d2.getFullYear() - d1.getFullYear()) * 12 + (d2.getMonth() - d1.getMonth());
    return meses > 0 ? meses : 0;
  };

  useEffect(() => {
    if (!projetoId) return;

    // Referência para a subcoleção: projetos/{projetoId}/bolsistas
    const bolsistasRef = collection(db, 'projetos', projetoId, 'bolsistas');
    const q = query(bolsistasRef);

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const data = snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      })) as Bolsista[];
      setBolsistas(data);
    });

    return () => unsubscribe();
  }, [projetoId]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const intersticioCalculado = calcularIntersticio(
      formData.dataInicio || '',
      formData.dataConclusao || ''
    );

    const novoBolsista = {
      ...formData,
      intersticio: intersticioCalculado,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    try {
      const bolsistasRef = collection(db, 'projetos', projetoId, 'bolsistas');
      await addDoc(bolsistasRef, novoBolsista);
      setFormData({ status: 'Em regularização' }); // Reset ao form
    } catch (error) {
      console.error("Erro ao adicionar bolsista: ", error);
    }
  };

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-4 text-slate-800">Gestão de Bolsistas</h2>

      {/* Formulário de Cadastro Simplificado */}
      <form onSubmit={handleSubmit} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 mb-8 grid grid-cols-1 md:grid-cols-2 gap-4">
        <input name="nome" placeholder="Nome" value={formData.nome || ''} onChange={handleInputChange} required className="border border-slate-200 p-3 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none" />
        <select name="status" value={formData.status} onChange={handleInputChange} className="border border-slate-200 p-3 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none bg-white">
          <option value="Em regularização">Em regularização</option>
          <option value="Ativo(a)">Ativo(a)</option>
          <option value="Concluído(a)">Concluído(a)</option>
          <option value="Desligado(a)">Desligado(a)</option>
        </select>
        <div className="flex flex-col">
            <label className="text-xs font-bold text-slate-500 mb-1 ml-1">Data Início</label>
            <input name="dataInicio" type="date" value={formData.dataInicio || ''} onChange={handleInputChange} required className="border border-slate-200 p-3 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none" />
        </div>
        <div className="flex flex-col">
            <label className="text-xs font-bold text-slate-500 mb-1 ml-1">Data Conclusão</label>
            <input name="dataConclusao" type="date" value={formData.dataConclusao || ''} onChange={handleInputChange} required className="border border-slate-200 p-3 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none" />
        </div>

        <input name="modalidadeBolsa" placeholder="Modalidade" value={formData.modalidadeBolsa || ''} onChange={handleInputChange} className="border border-slate-200 p-3 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none" />
        <input name="funcao" placeholder="Função" value={formData.funcao || ''} onChange={handleInputChange} className="border border-slate-200 p-3 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none" />
        <input name="agenciaBanestes" placeholder="Agência Banestes" value={formData.agenciaBanestes || ''} onChange={handleInputChange} className="border border-slate-200 p-3 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none" />
        <input name="contaBanestes" placeholder="Conta Banestes" value={formData.contaBanestes || ''} onChange={handleInputChange} className="border border-slate-200 p-3 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none" />

        {/* Interstício é exibido apenas para conferência visual, calculado na submissão */}
        <div className="col-span-1 md:col-span-2 text-sm text-slate-500 font-medium bg-slate-50 p-3 rounded-lg">
          Interstício calculado: <span className="font-bold text-slate-800">{calcularIntersticio(formData.dataInicio || '', formData.dataConclusao || '')} meses</span>
        </div>

        {/* Adicione os restantes campos mapeados na interface Bolsista conforme necessário */}

        <button type="submit" className="col-span-1 md:col-span-2 bg-blue-600 text-white p-3 rounded-xl hover:bg-blue-700 font-bold shadow-lg shadow-blue-100 transition-all uppercase tracking-wider text-xs">
          Salvar Bolsista
        </button>
      </form>

      {/* Tabela de Listagem */}
      <div className="overflow-x-auto rounded-2xl border border-slate-200 shadow-sm">
        <table className="min-w-full bg-white">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="p-4 text-left text-xs font-black text-slate-400 uppercase tracking-widest">Nome</th>
              <th className="p-4 text-left text-xs font-black text-slate-400 uppercase tracking-widest">Status</th>
              <th className="p-4 text-left text-xs font-black text-slate-400 uppercase tracking-widest">Início</th>
              <th className="p-4 text-left text-xs font-black text-slate-400 uppercase tracking-widest">Conclusão</th>
              <th className="p-4 text-left text-xs font-black text-slate-400 uppercase tracking-widest">Interstício</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {bolsistas.map(b => (
              <tr key={b.id} className="hover:bg-slate-50 transition-colors">
                <td className="p-4 text-sm font-bold text-slate-700">{b.nome}</td>
                <td className="p-4">
                  <span className={`px-2 py-1 rounded text-[10px] font-black uppercase tracking-widest ${
                    b.status === 'Ativo(a)' ? 'bg-green-100 text-green-700' :
                    b.status === 'Em regularização' ? 'bg-yellow-100 text-yellow-700' :
                    'bg-slate-100 text-slate-600'
                  }`}>
                    {b.status}
                  </span>
                </td>
                <td className="p-4 text-sm font-medium text-slate-600">{b.dataInicio ? new Date(b.dataInicio).toLocaleDateString('pt-BR') : '-'}</td>
                <td className="p-4 text-sm font-medium text-slate-600">{b.dataConclusao ? new Date(b.dataConclusao).toLocaleDateString('pt-BR') : '-'}</td>
                <td className="p-4 text-sm font-bold text-slate-700">{b.intersticio} meses</td>
              </tr>
            ))}
            {bolsistas.length === 0 && (
                <tr>
                    <td colSpan={5} className="p-8 text-center text-slate-400 text-sm font-medium italic">Nenhum bolsista cadastrado.</td>
                </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
