import React, { useState } from 'react';

interface NFSeData {
  cnpj: string;
  razaoSocial: string;
  municipio: string;
  uf: string;
}

export const NFSeGenerator = ({ onClose }: { onClose: () => void }) => {
  const [valorLiquido, setValorLiquido] = useState<string>('');
  const [mesReferencia, setMesReferencia] = useState<string>('');
  const [cnpj, setCnpj] = useState<string>('');
  
  const [loading, setLoading] = useState(false);
  const [clientData, setClientData] = useState<NFSeData | null>(null);
  
  const [showResults, setShowResults] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const cleanCnpj = (value: string) => value.replace(/\D/g, '');

  const formatCnpj = (value: string) => {
    const cleaned = cleanCnpj(value);
    if (cleaned.length <= 14) {
      return cleaned.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2}).*/, '$1.$2.$3/$4-$5');
    }
    return value;
  };

  const buscarCnpj = async () => {
    const cleanedCnpj = cleanCnpj(cnpj);
    if (cleanedCnpj.length !== 14) {
      alert('CNPJ inválido');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`https://brasilapi.com.br/api/cnpj/v1/${cleanedCnpj}`);
      if (!response.ok) throw new Error('CNPJ não encontrado');
      
      const data = await response.json();
      setClientData({
        cnpj: data.cnpj,
        razaoSocial: data.razao_social,
        municipio: data.municipio,
        uf: data.uf
      });
    } catch (error) {
      alert('Erro ao buscar CNPJ. Verifique se o número está correto.');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  // Cálculos
  const liquido = parseFloat(valorLiquido.replace(/\./g, '').replace(',', '.')) || 0;
  const valorBruto = liquido / 0.89;
  const inss = valorBruto * 0.11;
  const zeroStr = 'R$ 0,00';

  const formatCurrency = (val: number) => 
    val.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

  const descricao = `Desenvolvimento de soluções tecnológicas e consultoria em gestão empresarial na empresa ${clientData?.razaoSocial || '[RAZÃO SOCIAL]'}. Referente ao mês de ${mesReferencia || '[MÊS DE REFERÊNCIA]'}. Valor líquido acordado: ${formatCurrency(liquido)}.`;

  return (
    <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-[2rem] shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto border border-emerald-100 flex flex-col">
        
        {/* Header */}
        <div className="sticky top-0 bg-emerald-900 text-white p-6 md:p-8 flex justify-between items-center rounded-t-[2rem] z-10 shrink-0">
          <div>
            <h2 className="text-2xl font-black uppercase tracking-tighter text-emerald-100">Gerador de Dados NFS-e</h2>
            <p className="text-emerald-300/60 text-[10px] font-bold uppercase tracking-widest mt-1">
              Portal Nacional • Integração BrasilAPI
            </p>
          </div>
          <button 
            onClick={onClose}
            className="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="p-6 md:p-8 grid md:grid-cols-5 gap-8 overflow-y-auto">
          {/* Coluna Esquerda: Formulário */}
          <div className="md:col-span-2 space-y-6">
            <h3 className="text-[10px] font-black uppercase text-emerald-600 tracking-widest border-b border-emerald-100 pb-2">Entrada de Dados</h3>
            
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Valor Líquido Recebido (R$)</label>
              <input 
                type="text" 
                value={valorLiquido}
                onChange={(e) => setValorLiquido(e.target.value)}
                placeholder="Ex: 5000,00"
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-black text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Mês/Ano de Referência</label>
              <input 
                type="text" 
                value={mesReferencia}
                onChange={(e) => setMesReferencia(e.target.value)}
                placeholder="Ex: Janeiro/2026"
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <div className="space-y-3">
              <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider">CNPJ do Tomador</label>
              <div className="flex gap-2">
                <input 
                  type="text" 
                  value={formatCnpj(cnpj)}
                  onChange={(e) => setCnpj(e.target.value)}
                  placeholder="00.000.000/0000-00"
                  maxLength={18}
                  className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500"
                />
                <button 
                  onClick={buscarCnpj}
                  disabled={loading || cleanCnpj(cnpj).length !== 14}
                  className="bg-emerald-600 text-white px-4 rounded-xl font-black text-[10px] uppercase tracking-widest disabled:opacity-50 hover:bg-emerald-700 transition-colors flex items-center gap-2"
                >
                  {loading ? (
                    <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block"></span>
                  ) : (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                  )}
                </button>
              </div>
            </div>

            {clientData && (
              <div className="bg-emerald-50 p-4 rounded-xl border border-emerald-100 space-y-3">
                <h4 className="text-[10px] font-black uppercase text-emerald-800 tracking-widest flex justify-between items-center">
                  Dados do Cliente
                  <button onClick={() => setClientData(null)} className="text-emerald-500 hover:text-emerald-700">Editar Manualmente</button>
                </h4>
                
                <div className="group flex justify-between items-center">
                  <div>
                    <span className="block text-[9px] font-bold text-emerald-600 uppercase">Razão Social</span>
                    <span className="text-sm font-bold text-slate-800">{clientData.razaoSocial}</span>
                  </div>
                </div>
                
                <div className="group flex justify-between items-center">
                  <div>
                    <span className="block text-[9px] font-bold text-emerald-600 uppercase">Município/UF</span>
                    <span className="text-sm font-bold text-slate-800">{clientData.municipio} - {clientData.uf}</span>
                  </div>
                </div>
              </div>
            )}

            <button
              onClick={() => setShowResults(true)}
              disabled={!valorLiquido || !mesReferencia}
              className="w-full bg-slate-900 text-white py-4 rounded-xl font-black text-xs uppercase tracking-widest mt-4 hover:bg-slate-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg"
            >
              Gerar Dados para NFS-e
            </button>
          </div>

          {/* Coluna Direita: Resultados */}
          <div className="md:col-span-3 bg-slate-50 p-6 rounded-2xl border border-slate-200 relative">
            {!showResults ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400 opacity-50 p-6 text-center">
                <svg className="w-16 h-16 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                <p className="font-bold text-sm uppercase tracking-widest">Preencha os dados ao lado para gerar o espelho da nota</p>
              </div>
            ) : (
              <div className="space-y-6 animate-in slide-in-from-right-4">
                
                {/* Copiar Block Helper */}
                <div className="flex items-center gap-2 mb-2">
                    <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                    <span className="text-[10px] font-black uppercase tracking-widest text-emerald-600">Espelho Gerado (Pronto para copiar)</span>
                </div>

                <div className="space-y-6">
                    {/* Linha 1: Códigos */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-white p-4 rounded-xl border border-slate-200">
                            <span className="block text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">CNPJ do Tomador</span>
                            <div className="flex justify-between items-center">
                                <span className="text-sm font-black text-slate-800">{clientData?.cnpj || cnpj}</span>
                                <button 
                                    onClick={() => handleCopy(cleanCnpj(clientData?.cnpj || cnpj), 'cnpj')}
                                    className={`p-2 rounded-lg transition-colors ${copiedField === 'cnpj' ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-50 hover:bg-slate-100 text-slate-500'}`}
                                >
                                    {copiedField === 'cnpj' ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>}
                                </button>
                            </div>
                        </div>

                        <div className="bg-white p-4 rounded-xl border border-slate-200">
                            <span className="block text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">Código de Tributação</span>
                            <div className="flex justify-between items-center">
                                <span className="text-sm font-black text-slate-800">17.01</span>
                                <button 
                                    onClick={() => handleCopy('17.01', 'codigo')}
                                    className={`p-2 rounded-lg transition-colors ${copiedField === 'codigo' ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-50 hover:bg-slate-100 text-slate-500'}`}
                                >
                                    {copiedField === 'codigo' ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>}
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* Descrição do Serviço */}
                    <div className="bg-white p-4 rounded-xl border border-slate-200">
                        <div className="flex justify-between items-start mb-2">
                            <span className="block text-[9px] font-bold text-slate-400 uppercase tracking-widest">Descrição do Serviço</span>
                            <button 
                                onClick={() => handleCopy(descricao, 'descricao')}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-colors ${copiedField === 'descricao' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 hover:bg-slate-200 text-slate-600'}`}
                            >
                                {copiedField === 'descricao' ? (
                                    <><svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> Copiado!</>
                                ) : (
                                    <><svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg> Copiar Texto</>
                                )}
                            </button>
                        </div>
                        <p className="text-sm font-semibold text-slate-800 leading-relaxed bg-slate-50 p-3 rounded-lg border border-slate-100">
                            {descricao}
                        </p>
                    </div>

                    {/* Valores Críticos */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-emerald-50 p-5 rounded-xl border border-emerald-200 relative overflow-hidden group">
                            <span className="block text-[9px] font-black text-emerald-700 uppercase tracking-widest mb-1">Valor Bruto (Serviço)</span>
                            <div className="text-2xl font-black text-emerald-900">{formatCurrency(valorBruto)}</div>
                            <button 
                                onClick={() => handleCopy(valorBruto.toFixed(2).replace('.', ','), 'bruto')}
                                className="absolute top-4 right-4 p-2 bg-white/80 rounded-lg text-emerald-600 opacity-0 group-hover:opacity-100 hover:bg-white transition-all shadow-sm"
                            >
                                {copiedField === 'bruto' ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>}
                            </button>
                        </div>

                        <div className="bg-rose-50 p-5 rounded-xl border border-rose-200 relative overflow-hidden group">
                            <span className="block text-[9px] font-black text-rose-700 uppercase tracking-widest mb-1">Valor INSS Retido (11%)</span>
                            <div className="text-2xl font-black text-rose-900">{formatCurrency(inss)}</div>
                            <button 
                                onClick={() => handleCopy(inss.toFixed(2).replace('.', ','), 'inss')}
                                className="absolute top-4 right-4 p-2 bg-white/80 rounded-lg text-rose-600 opacity-0 group-hover:opacity-100 hover:bg-white transition-all shadow-sm"
                            >
                                {copiedField === 'inss' ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>}
                            </button>
                        </div>
                    </div>

                    {/* Outros Impostos Zerados */}
                    <div className="bg-white p-4 rounded-xl border border-slate-200 border-dashed">
                        <span className="block text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-3 text-center">ISS, PIS, COFINS, CSLL e IR retidos</span>
                        <div className="grid grid-cols-5 gap-2">
                           {['ISS', 'PIS', 'COFINS', 'CSLL', 'IR'].map(imposto => (
                               <div key={imposto} className="text-center group">
                                   <div className="text-[10px] font-black text-slate-500 uppercase">{imposto}</div>
                                   <div className="text-xs font-bold text-slate-400 mt-1 cursor-pointer hover:text-emerald-500 transition-colors" onClick={() => handleCopy('0,00', `imposto_${imposto}`)}>0,00</div>
                               </div>
                           ))}
                        </div>
                    </div>

                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
