import React, { useEffect, useState } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../../../firebase';
import { Projeto } from '../../../types';

export const PublicScholarshipRegistration: React.FC = () => {
  const pathParts = window.location.pathname.split('/');
  const projectId = pathParts[2];
  const token = pathParts[3];

  const [project, setProject] = useState<Projeto | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [formData, setFormData] = useState({
    nome: '',
    cpf: '',
    rg: '',
    email: '',
    telefone: '',
    endereco: '',
    lattes: '',
    banco: '',
    agencia: '',
    conta: '',
    chave_pix: '',
    campus: '',
    curso: '',
  });

  useEffect(() => {
    const fetchProject = async () => {
      if (!projectId || !token) {
        setError('Link invalido: projeto ou token ausente.');
        setIsLoading(false);
        return;
      }

      try {
        const fn = httpsCallable(functions, 'getPublicScholarshipProject');
        const response = await fn({ projectId, token });
        const data = response.data as { valid: boolean; project: Projeto };
        setProject(data.project);
      } catch (err) {
        console.error(err);
        setError('Projeto nao encontrado ou link expirado.');
      } finally {
        setIsLoading(false);
      }
    };

    void fetchProject();
  }, [projectId, token]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const formatCPF = (value: string) =>
    value
      .replace(/\D/g, '')
      .replace(/(\d{3})(\d)/, '$1.$2')
      .replace(/(\d{3})(\d)/, '$1.$2')
      .replace(/(\d{3})(\d{1,2})/, '$1-$2')
      .replace(/(-\d{2})\d+?$/, '$1');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const fn = httpsCallable(functions, 'submitPublicScholarshipRegistration');
      await fn({
        projectId,
        token,
        formData,
      });
      setSuccess(true);
    } catch (err) {
      console.error(err);
      setError('Ocorreu um erro ao salvar seus dados. Tente novamente.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-400 font-bold">Carregando...</div>;
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
        <div className="bg-white max-w-md w-full p-8 rounded-[2rem] shadow-xl text-center">
          <div className="w-20 h-20 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto mb-6">
            <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
          </div>
          <h2 className="text-2xl font-black text-slate-900 mb-2">Cadastro Realizado!</h2>
          <p className="text-slate-500 mb-6">Seus dados foram enviados para a coordenacao do projeto <strong>{project?.nome}</strong>. Aguarde o contato para formalizacao.</p>
          <button onClick={() => window.location.reload()} className="text-indigo-600 font-bold hover:underline">Voltar</button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-10">
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">Portal do Bolsista</h1>
          {project && <p className="mt-2 text-lg text-slate-600">Autocadastro para: <span className="font-bold text-indigo-600">{project.nome}</span></p>}
        </div>

        {error && (
          <div className="mb-6 bg-rose-50 border border-rose-200 text-rose-600 px-4 py-3 rounded-xl text-sm font-bold text-center">
            {error}
          </div>
        )}

        <div className="bg-white rounded-[2rem] shadow-xl border border-slate-200 overflow-hidden">
          <div className="bg-slate-900 px-8 py-6">
            <h3 className="text-white font-bold text-lg flex items-center gap-2">
              <svg className="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
              Dados Pessoais
            </h3>
            <p className="text-slate-400 text-xs mt-1">Preencha com atencao. Estes dados serao usados para seu contrato.</p>
          </div>

          <form onSubmit={handleSubmit} className="p-8 space-y-8">
            <div className="space-y-4">
              <h4 className="text-xs font-black text-slate-400 uppercase tracking-widest border-b border-slate-100 pb-2">Identificacao</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="md:col-span-2">
                  <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Nome Completo</label>
                  <input name="nome" required value={formData.nome} onChange={handleInputChange} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-bold text-slate-800" placeholder="Conforme documento oficial" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">CPF</label>
                  <input
                    name="cpf"
                    required
                    value={formData.cpf}
                    onChange={(e) => setFormData((prev) => ({ ...prev, cpf: formatCPF(e.target.value) }))}
                    maxLength={14}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-bold text-slate-800"
                    placeholder="000.000.000-00"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">RG</label>
                  <input name="rg" required value={formData.rg} onChange={handleInputChange} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-bold text-slate-800" />
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <h4 className="text-xs font-black text-slate-400 uppercase tracking-widest border-b border-slate-100 pb-2">Contato e Endereco</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">E-mail</label>
                  <input name="email" type="email" required value={formData.email} onChange={handleInputChange} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Telefone (WhatsApp)</label>
                  <input name="telefone" required value={formData.telefone} onChange={handleInputChange} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700" />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Endereco</label>
                  <textarea name="endereco" required value={formData.endereco} onChange={handleInputChange} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700 min-h-[110px]" />
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <h4 className="text-xs font-black text-slate-400 uppercase tracking-widest border-b border-slate-100 pb-2">Formacao</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Campus</label>
                  <input name="campus" value={formData.campus} onChange={handleInputChange} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Curso</label>
                  <input name="curso" value={formData.curso} onChange={handleInputChange} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700" />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Link do Lattes</label>
                  <input name="lattes" value={formData.lattes} onChange={handleInputChange} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700" />
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <h4 className="text-xs font-black text-slate-400 uppercase tracking-widest border-b border-slate-100 pb-2">Dados Bancarios</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Banco</label>
                  <input name="banco" value={formData.banco} onChange={handleInputChange} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Agencia</label>
                  <input name="agencia" value={formData.agencia} onChange={handleInputChange} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Conta</label>
                  <input name="conta" value={formData.conta} onChange={handleInputChange} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Chave PIX</label>
                  <input name="chave_pix" value={formData.chave_pix} onChange={handleInputChange} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700" />
                </div>
              </div>
            </div>

            <div className="pt-2 flex items-center justify-end gap-3">
              <button type="submit" disabled={isSubmitting} className="bg-indigo-600 text-white px-8 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-indigo-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed">
                {isSubmitting ? 'Enviando...' : 'Enviar Cadastro'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
