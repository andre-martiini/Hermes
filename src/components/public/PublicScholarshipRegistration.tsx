import React, { useState, useEffect } from 'react';
import { collection, query, where, getDocs, addDoc, updateDoc, doc, getDoc } from 'firebase/firestore';
import { db } from '../../../firebase';
import { PerfilPessoa, VinculoProjeto, Projeto } from '../../../types';

export const PublicScholarshipRegistration: React.FC = () => {
    // Extract projectId from URL manually since we don't have react-router hooks
    // URL format: /join/:projectId/:token
    const pathParts = window.location.pathname.split('/');
    const projectId = pathParts[2];
    const token = pathParts[3]; // We could use this for validation if needed

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
        curso: ''
    });

    useEffect(() => {
        const fetchProject = async () => {
            if (!projectId) {
                setError("Link inválido: ID do projeto não encontrado.");
                setIsLoading(false);
                return;
            }
            try {
                const docRef = doc(db, 'projetos', projectId);
                const docSnap = await getDoc(docRef);
                if (docSnap.exists()) {
                    setProject({ id: docSnap.id, ...docSnap.data() } as Projeto);
                } else {
                    setError("Projeto não encontrado ou link expirado.");
                }
            } catch (err) {
                console.error(err);
                setError("Erro ao carregar dados do projeto.");
            } finally {
                setIsLoading(false);
            }
        };
        fetchProject();
    }, [projectId]);

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    const formatCPF = (value: string) => {
        return value
            .replace(/\D/g, '')
            .replace(/(\d{3})(\d)/, '$1.$2')
            .replace(/(\d{3})(\d)/, '$1.$2')
            .replace(/(\d{3})(\d{1,2})/, '$1-$2')
            .replace(/(-\d{2})\d+?$/, '$1');
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsSubmitting(true);
        setError(null);

        try {
            // 1. Check if PerfilPessoa already exists by CPF
            const pessoasRef = collection(db, 'perfil_pessoas');
            const q = query(pessoasRef, where('cpf', '==', formData.cpf));
            const querySnapshot = await getDocs(q);

            let pessoaId: string;

            const perfilData = {
                nome: formData.nome,
                cpf: formData.cpf,
                rg: formData.rg,
                email: formData.email,
                telefone: formData.telefone,
                endereco: formData.endereco,
                lattes: formData.lattes,
                campus: formData.campus,
                curso: formData.curso,
                dados_bancarios: {
                    banco: formData.banco,
                    agencia: formData.agencia,
                    conta: formData.conta,
                    chave_pix: formData.chave_pix
                },
                data_atualizacao: new Date().toISOString()
            };

            if (!querySnapshot.empty) {
                // Update existing
                const docSnap = querySnapshot.docs[0];
                pessoaId = docSnap.id;
                await updateDoc(doc(db, 'perfil_pessoas', pessoaId), perfilData);
            } else {
                // Create new
                const newDoc = await addDoc(pessoasRef, {
                    ...perfilData,
                    data_criacao: new Date().toISOString()
                });
                pessoaId = newDoc.id;
            }

            // 2. Create VinculoProjeto (Pending)
            // Check if already linked to this project to avoid duplicates?
            // For now, let's assume multiple links are possible or handled by admin approval.
            // But to prevent spam, we might want to check for an active pending link.
            const vinculosRef = collection(db, 'vinculos_projeto');
            const qLink = query(
                vinculosRef,
                where('projeto_id', '==', projectId),
                where('pessoa_id', '==', pessoaId),
                where('status', '==', 'Em regularização')
            );
            const linkSnap = await getDocs(qLink);

            if (linkSnap.empty) {
                const vinculo: Partial<VinculoProjeto> = {
                    pessoa_id: pessoaId,
                    projeto_id: projectId!,
                    data_inicio: new Date().toISOString().split('T')[0], // Default to today as placeholder
                    data_fim_prevista: '', // Admin sets this
                    status: 'Em regularização',
                    tipo_bolsa_id: '', // Admin sets this
                    percentual_recebimento: 100,
                    valor_bolsa_mensal_atual: 0 // Admin sets this
                };
                await addDoc(vinculosRef, vinculo);
            }

            setSuccess(true);
        } catch (err) {
            console.error(err);
            setError("Ocorreu um erro ao salvar seus dados. Tente novamente.");
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
                    <p className="text-slate-500 mb-6">Seus dados foram enviados para a coordenação do projeto <strong>{project?.nome}</strong>. Aguarde o contato para formalização.</p>
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
                        <p className="text-slate-400 text-xs mt-1">Preencha com atenção. Estes dados serão usados para seu contrato.</p>
                    </div>

                    <form onSubmit={handleSubmit} className="p-8 space-y-8">
                        {/* Identificação */}
                        <div className="space-y-4">
                            <h4 className="text-xs font-black text-slate-400 uppercase tracking-widest border-b border-slate-100 pb-2">Identificação</h4>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                <div className="md:col-span-2">
                                    <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Nome Completo</label>
                                    <input
                                        name="nome"
                                        required
                                        value={formData.nome}
                                        onChange={handleInputChange}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-bold text-slate-800"
                                        placeholder="Conforme documento oficial"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">CPF</label>
                                    <input
                                        name="cpf"
                                        required
                                        value={formData.cpf}
                                        onChange={(e) => {
                                            const val = formatCPF(e.target.value);
                                            setFormData(prev => ({ ...prev, cpf: val }));
                                        }}
                                        maxLength={14}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-bold text-slate-800"
                                        placeholder="000.000.000-00"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">RG</label>
                                    <input
                                        name="rg"
                                        required
                                        value={formData.rg}
                                        onChange={handleInputChange}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-bold text-slate-800"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Contato */}
                        <div className="space-y-4">
                            <h4 className="text-xs font-black text-slate-400 uppercase tracking-widest border-b border-slate-100 pb-2">Contato & Endereço</h4>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">E-mail</label>
                                    <input
                                        name="email"
                                        type="email"
                                        required
                                        value={formData.email}
                                        onChange={handleInputChange}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Telefone (WhatsApp)</label>
                                    <input
                                        name="telefone"
                                        required
                                        value={formData.telefone}
                                        onChange={handleInputChange}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700"
                                        placeholder="(00) 00000-0000"
                                    />
                                </div>
                                <div className="md:col-span-2">
                                    <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Endereço Completo</label>
                                    <textarea
                                        name="endereco"
                                        required
                                        rows={2}
                                        value={formData.endereco}
                                        onChange={handleInputChange}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700 resize-none"
                                        placeholder="Rua, Número, Bairro, Cidade - UF, CEP"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Acadêmico & Bancário */}
                        <div className="space-y-4">
                            <h4 className="text-xs font-black text-slate-400 uppercase tracking-widest border-b border-slate-100 pb-2">Dados Bancários & Acadêmicos</h4>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Banco</label>
                                    <input
                                        name="banco"
                                        required
                                        value={formData.banco}
                                        onChange={handleInputChange}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700"
                                        placeholder="Ex: Banestes, Nubank..."
                                    />
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Agência</label>
                                        <input
                                            name="agencia"
                                            required
                                            value={formData.agencia}
                                            onChange={handleInputChange}
                                            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Conta</label>
                                        <input
                                            name="conta"
                                            required
                                            value={formData.conta}
                                            onChange={handleInputChange}
                                            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700"
                                        />
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Chave PIX (Preferencial)</label>
                                    <input
                                        name="chave_pix"
                                        value={formData.chave_pix}
                                        onChange={handleInputChange}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 mb-1 ml-1">Link Currículo Lattes</label>
                                    <input
                                        name="lattes"
                                        value={formData.lattes}
                                        onChange={handleInputChange}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-blue-600 underline"
                                        placeholder="http://lattes.cnpq.br/..."
                                    />
                                </div>
                            </div>
                        </div>

                        <div className="pt-6">
                            <button
                                type="submit"
                                disabled={isSubmitting}
                                className={`w-full bg-indigo-600 text-white py-4 rounded-xl font-black uppercase tracking-widest shadow-lg shadow-indigo-200 hover:bg-indigo-700 transition-all ${isSubmitting ? 'opacity-70 cursor-wait' : ''}`}
                            >
                                {isSubmitting ? 'Enviando...' : 'Confirmar Cadastro'}
                            </button>
                            <p className="text-center text-xs text-slate-400 mt-4">
                                Ao enviar, você concorda com o uso destes dados para fins de gestão do projeto.
                            </p>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    );
};
