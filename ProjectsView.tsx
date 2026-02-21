import React, { useState, useEffect } from 'react';
import { collection, onSnapshot, query, addDoc, orderBy } from 'firebase/firestore';
import { db } from './firebase';
import { Projeto } from './types';
import { BolsistasView } from './BolsistasView';

export const ProjectsView: React.FC = () => {
  const [projects, setProjects] = useState<Projeto[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDesc, setNewProjectDesc] = useState('');

  useEffect(() => {
    const q = query(collection(db, 'projetos'), orderBy('data_criacao', 'desc'));
    const unsubscribe = onSnapshot(q, (snapshot) => {
      const data = snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      })) as Projeto[];
      setProjects(data);
    });
    return () => unsubscribe();
  }, []);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;

    try {
      await addDoc(collection(db, 'projetos'), {
        nome: newProjectName,
        descricao: newProjectDesc,
        data_criacao: new Date().toISOString()
      });
      setNewProjectName('');
      setNewProjectDesc('');
      setIsCreating(false);
    } catch (error) {
      console.error("Error creating project:", error);
    }
  };

  if (selectedProjectId) {
    return (
      <div className="animate-in fade-in slide-in-from-right duration-300">
        <button
          onClick={() => setSelectedProjectId(null)}
          className="mb-4 flex items-center gap-2 text-slate-500 hover:text-slate-800 font-bold text-xs uppercase tracking-widest transition-colors px-6 md:px-0"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
          Voltar para Projetos
        </button>
        <div className="bg-white border border-slate-200 rounded-none md:rounded-[2.5rem] overflow-hidden shadow-xl min-h-[600px]">
             {/* Header do Projeto */}
             <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
                <div>
                    <h3 className="text-2xl font-black text-slate-900 tracking-tight">
                        {projects.find(p => p.id === selectedProjectId)?.nome || 'Projeto'}
                    </h3>
                    <p className="text-slate-400 text-xs font-bold uppercase tracking-widest mt-1">
                        {projects.find(p => p.id === selectedProjectId)?.descricao || 'Sem descrição'}
                    </p>
                </div>
             </div>
            <BolsistasView projetoId={selectedProjectId} />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-20">
      <div className="bg-white p-8 rounded-none md:rounded-[2rem] border border-slate-200 shadow-xl">
        <h3 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-3">
          <span className="w-2 h-8 bg-indigo-500 rounded-full"></span>
          Projetos & Programas
        </h3>
        <p className="text-slate-400 text-xs font-bold uppercase tracking-widest mt-1 ml-5">Gestão de Bolsistas e Atividades</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 px-4 md:px-0">
        {/* Card Novo Projeto */}
        <button
          onClick={() => setIsCreating(true)}
          className="group border-2 border-dashed border-slate-300 rounded-[2rem] p-8 flex flex-col items-center justify-center gap-4 hover:border-indigo-400 hover:bg-indigo-50/50 transition-all min-h-[200px]"
        >
          <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center group-hover:bg-indigo-100 group-hover:text-indigo-600 text-slate-400 transition-colors">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" /></svg>
          </div>
          <span className="text-sm font-black text-slate-400 group-hover:text-indigo-600 uppercase tracking-widest">Novo Projeto</span>
        </button>

        {/* Lista de Projetos */}
        {projects.map(project => (
          <div
            key={project.id}
            onClick={() => setSelectedProjectId(project.id)}
            className="group bg-white border border-slate-200 rounded-[2rem] p-8 hover:shadow-xl hover:border-indigo-300 transition-all cursor-pointer relative overflow-hidden"
          >
            <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>

            <div className="relative z-10 space-y-4">
                <div className="w-12 h-12 bg-indigo-100 text-indigo-600 rounded-2xl flex items-center justify-center">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>
                </div>
                <div>
                    <h4 className="text-xl font-black text-slate-800 group-hover:text-indigo-700 transition-colors line-clamp-1">{project.nome}</h4>
                    <p className="text-xs font-medium text-slate-500 line-clamp-2 mt-1 min-h-[2.5em]">{project.descricao || 'Sem descrição'}</p>
                </div>
                <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
                    <span className="text-[10px] font-bold text-slate-300 uppercase tracking-widest">
                        {new Date(project.data_criacao).toLocaleDateString('pt-BR')}
                    </span>
                    <div className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center group-hover:bg-indigo-500 group-hover:text-white transition-colors">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
                    </div>
                </div>
            </div>
          </div>
        ))}
      </div>

      {/* Modal de Criação */}
      {isCreating && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
            <div className="bg-white w-full max-w-md rounded-[2rem] shadow-2xl p-8 animate-in zoom-in-95">
                <h3 className="text-xl font-black text-slate-900 mb-6">Criar Novo Projeto</h3>
                <form onSubmit={handleCreateProject} className="space-y-4">
                    <div>
                        <label className="text-xs font-bold text-slate-500 ml-1">Nome do Projeto</label>
                        <input
                            value={newProjectName}
                            onChange={e => setNewProjectName(e.target.value)}
                            className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 outline-none focus:ring-2 focus:ring-indigo-500 font-bold text-slate-800 mt-1"
                            placeholder="Ex: Bolsa Permanência 2024"
                            autoFocus
                        />
                    </div>
                    <div>
                        <label className="text-xs font-bold text-slate-500 ml-1">Descrição</label>
                        <textarea
                            value={newProjectDesc}
                            onChange={e => setNewProjectDesc(e.target.value)}
                            className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-600 mt-1 resize-none"
                            placeholder="Breve descrição do projeto..."
                            rows={3}
                        />
                    </div>
                    <div className="flex gap-3 pt-4">
                        <button
                            type="button"
                            onClick={() => setIsCreating(false)}
                            className="flex-1 py-3 text-xs font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-xl transition-all"
                        >
                            Cancelar
                        </button>
                        <button
                            type="submit"
                            className="flex-1 bg-indigo-600 text-white py-3 rounded-xl text-xs font-black uppercase tracking-widest shadow-lg hover:bg-indigo-700 transition-all"
                        >
                            Criar
                        </button>
                    </div>
                </form>
            </div>
        </div>
      )}
    </div>
  );
};
export default ProjectsView;
