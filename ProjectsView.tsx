import React, { useState, useEffect } from 'react';
import { collection, onSnapshot, query, addDoc, orderBy, getDocs, where } from 'firebase/firestore';
import { db } from './firebase';
import { Projeto, VinculoProjeto, ItemOrcamento, TransacaoProjeto, RemanejamentoRecursos } from './types';
import { BolsistasView } from './BolsistasView';
import { ProjectBudgetView } from './ProjectBudgetView';
import { AcquisitionsView } from './AcquisitionsView';
import { AutoExpandingTextarea } from './src/components/ui/UIComponents';

import { generateMarkdown, downloadMarkdown } from './src/utils/markdownGenerator';

export const ProjectsView = ({
  projects,
  isCreating,
  onCloseCreate,
  onCreateProject
}: {
  projects: Projeto[],
  isCreating: boolean,
  onCloseCreate: () => void,
  onCreateProject: (name: string, desc: string) => Promise<void>
}) => {
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDesc, setNewProjectDesc] = useState('');
  const [activeTab, setActiveTab] = useState<'bolsistas' | 'orcamento' | 'aquisicoes'>('bolsistas');

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    await onCreateProject(newProjectName, newProjectDesc);
    setNewProjectName('');
    setNewProjectDesc('');
  };

  const handleExportProject = async (project: Projeto) => {
    try {
      // 1. Fetch Related Data
      const vinculosSnap = await getDocs(query(collection(db, 'vinculos_projeto'), where('projeto_id', '==', project.id)));
      const vinculos = vinculosSnap.docs.map(doc => ({ id: doc.id, ...doc.data() } as VinculoProjeto));

      const orcamentoItemsSnap = await getDocs(collection(db, `projetos/${project.id}/itens_orcamento`));
      const orcamentoItems = orcamentoItemsSnap.docs.map(doc => ({ id: doc.id, ...doc.data() } as ItemOrcamento));

      const transacoesSnap = await getDocs(query(collection(db, 'transacoes_projeto'), where('projeto_id', '==', project.id)));
      const transacoes = transacoesSnap.docs.map(doc => ({ id: doc.id, ...doc.data() } as TransacaoProjeto));

      const remanejamentosSnap = await getDocs(query(collection(db, 'remanejamentos_recursos'), where('projeto_id', '==', project.id)));
      const remanejamentos = remanejamentosSnap.docs.map(doc => ({ id: doc.id, ...doc.data() } as RemanejamentoRecursos));

      // 2. Build Sections for Markdown
      const dataSections = [
        { title: 'Dados Gerais', data: [project] },
        { title: 'Bolsistas Vinculados', data: vinculos },
        { title: 'Itens de Orçamento Planejados', data: orcamentoItems },
        { title: 'Transações e Pagamentos', data: transacoes },
        { title: 'Remanejamentos de Recursos', data: remanejamentos }
      ];

      const md = generateMarkdown(
        `Projeto: ${project.nome}`,
        project.descricao || 'Sem descrição.',
        {
          'Nome': 'Nome do projeto',
          'Descrição': 'Descrição detalhada',
          'id': 'ID do Registro',
          'data_criacao': 'Criado em',
          'data_inicio': 'Início',
          'data_fim_prevista': 'Fim Previsto',
          'status': 'Status Atual',
          'valor_real': 'Valor Pago',
          'rubrica': 'Rubrica',
          'quantidade': 'Qtd',
          'valor': 'Valor Movimentado'
        },
        dataSections
      );
      downloadMarkdown(`projeto_${project.nome.replace(/\s+/g, '_')}`, md);
    } catch (error) {
      console.error("Erro ao exportar projeto:", error);
    }
  };

  if (selectedProjectId) {
    const project = projects.find(p => p.id === selectedProjectId);
    return (
      <div className="px-4 md:px-0">
        <button
          onClick={() => setSelectedProjectId(null)}
          className="mb-6 flex items-center gap-2 text-slate-400 hover:text-indigo-600 font-black text-[10px] uppercase tracking-[0.2em] transition-all group"
        >
          <svg className="w-4 h-4 group-hover:-translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
          Voltar para Projetos
        </button>
        
        <div className="bg-white border border-slate-200 rounded-[2.5rem] overflow-hidden shadow-2xl min-h-[700px]">
             {/* Header do Projeto - Estilo Premium */}
             <div className="p-10 border-b border-slate-100 bg-slate-50/30 flex items-center justify-between">
                <div>
                    <div className="flex items-center gap-3 mb-2">
                      <span className="px-3 py-1 bg-indigo-100 text-indigo-600 rounded-full text-[9px] font-black uppercase tracking-widest">Projeto Ativo</span>
                    </div>
                    <h3 className="text-3xl font-black text-slate-900 tracking-tighter">
                        {project?.nome || 'Projeto'}
                    </h3>
                    <p className="text-slate-400 text-sm font-medium mt-1">
                        {project?.descricao || 'Gestão de bolsistas e recursos do projeto.'}
                    </p>
                </div>
                
                <div className="flex gap-4 items-center">
                  <div className="hidden md:block text-right">
                    <p className="text-[9px] font-black text-slate-300 uppercase tracking-widest">Data de Início</p>
                    <p className="text-sm font-bold text-slate-700">{project?.data_criacao ? new Date(project.data_criacao).toLocaleDateString('pt-BR') : '-'}</p>
                  </div>
                  <button onClick={() => project && handleExportProject(project)} className="p-2 text-slate-400 hover:text-indigo-600 transition-colors" title="Exportar Projeto">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4-4m0 0l-4-4m4 4v12" /></svg>
                  </button>
                </div>
             </div>

             {/* Abas de Navegação */}
             <div className="px-10 border-b border-slate-100 flex gap-6 overflow-x-auto">
                <button
                    onClick={() => setActiveTab('bolsistas')}
                    className={`py-4 text-xs font-black uppercase tracking-widest border-b-2 transition-colors whitespace-nowrap ${activeTab === 'bolsistas' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                >
                    Gestão de Bolsistas
                </button>
                <button
                    onClick={() => setActiveTab('orcamento')}
                    className={`py-4 text-xs font-black uppercase tracking-widest border-b-2 transition-colors whitespace-nowrap ${activeTab === 'orcamento' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                >
                    Planejamento Orçamental
                </button>
                <button
                    onClick={() => setActiveTab('aquisicoes')}
                    className={`py-4 text-xs font-black uppercase tracking-widest border-b-2 transition-colors whitespace-nowrap ${activeTab === 'aquisicoes' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                >
                    Aquisições e Compliance
                </button>
             </div>

             <div className="bg-white">
                {activeTab === 'bolsistas' ? (
                    <BolsistasView projetoId={selectedProjectId} />
                ) : activeTab === 'orcamento' ? (
                    <ProjectBudgetView projetoId={selectedProjectId} />
                ) : (
                    <AcquisitionsView projetoId={selectedProjectId} />
                )}
             </div>
        </div>
      </div>
    );
  }


  return (
    <div className="space-y-8 pb-20 px-4 md:px-0">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Lista de Projetos */}
        {projects.map(project => (
          <div
            key={project.id}
            onClick={() => setSelectedProjectId(project.id)}
            className="group bg-white border border-slate-200 rounded-[2.5rem] p-8 hover:shadow-2xl hover:border-indigo-400/50 transition-all cursor-pointer relative overflow-hidden"
          >
            <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>

            <div className="relative z-10 space-y-5">
                <div className="w-14 h-14 bg-indigo-50 text-indigo-600 rounded-2xl flex items-center justify-center group-hover:bg-indigo-600 group-hover:text-white transition-all duration-300 shadow-sm">
                    <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>
                </div>
                <div>
                    <h4 className="text-xl font-black text-slate-800 group-hover:text-indigo-700 transition-colors line-clamp-1">{project.nome}</h4>
                    <p className="text-xs font-semibold text-slate-400 line-clamp-2 mt-1 min-h-[2.5em] leading-relaxed">{project.descricao || 'Sem descrição detalhada disponível.'}</p>
                </div>
                <div className="pt-5 border-t border-slate-100 flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="text-[9px] font-black text-slate-300 uppercase tracking-[0.2em]">Criado em</span>
                      <span className="text-xs font-bold text-slate-500 uppercase">
                          {new Date(project.data_criacao).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })}
                      </span>
                    </div>
                    <div className="w-10 h-10 rounded-full bg-slate-50 flex items-center justify-center group-hover:bg-indigo-600 group-hover:text-white transition-all duration-300 shadow-inner">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
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
                        <AutoExpandingTextarea
                            value={newProjectDesc}
                            onChange={e => setNewProjectDesc(e.target.value)}
                            className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-600 mt-1"
                            placeholder="Breve descrição do projeto..."
                            rows={3}
                        />
                    </div>
                    <div className="flex gap-3 pt-4">
                        <button
                            type="button"
                            onClick={onCloseCreate}
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
