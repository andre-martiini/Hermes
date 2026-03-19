import React, { useState, useEffect } from 'react';
import { db } from '../../firebase';
import { doc, setDoc, onSnapshot } from 'firebase/firestore';

interface NFSeData {
  cnpj: string;
  razaoSocial: string;
  municipio: string;
  uf: string;
}

export const NFSeGenerator = ({ onClose }: { onClose: () => void }) => {
  const [valorLiquido, setValorLiquido] = useState<string>('');
  
  const monthNames = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
  ];

  const today = new Date();
  const [selecaoMes, setSelecaoMes] = useState<number>(today.getMonth() + 1);
  const [selecaoAno, setSelecaoAno] = useState<number>(today.getFullYear());
  
  const [dataCompetencia, setDataCompetencia] = useState<string>(() => {
    const day = '10';
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const year = today.getFullYear();
    return `${day}${month}${year}`;
  });
  const [cnpj, setCnpj] = useState<string>('');
  
  // States for calculated/editable values
  const [valorBrutoManual, setValorBrutoManual] = useState<string | null>(null);
  const [valorCPManual, setValorCPManual] = useState<string | null>(null);
  const [valorIRRFManual, setValorIRRFManual] = useState<string | null>(null);
  const [descricaoManual, setDescricaoManual] = useState<string | null>(null);
  const [portalLogin, setPortalLogin] = useState<string>('');
  const [portalSenha, setPortalSenha] = useState<string>('');

  const [loading, setLoading] = useState(false);
  const [clientData, setClientData] = useState<NFSeData | null>(null);
  
  const [showResults, setShowResults] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [isRobotRunning, setIsRobotRunning] = useState(false);

  const cleanCnpj = (value: string) => value.replace(/\D/g, '');

  const formatCnpj = (value: string) => {
    const cleaned = cleanCnpj(value);
    if (cleaned.length <= 14) {
      return cleaned.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2}).*/, '$1.$2.$3/$4-$5');
    }
    return value;
  };

  const formatDataCompetenciaDisplay = (val: string) => {
    const clean = val.replace(/\D/g, '');
    if (clean.length <= 2) return clean;
    if (clean.length <= 4) return `${clean.slice(0, 2)}/${clean.slice(2)}`;
    return `${clean.slice(0, 2)}/${clean.slice(2, 4)}/${clean.slice(4, 8)}`;
  };

  const handleDataCompetenciaChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const clean = e.target.value.replace(/\D/g, '').slice(0, 8);
    setDataCompetencia(clean);
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

  const formatCurrency = (val: number) => 
    val.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

  // Cálculos Automáticos
  const liquidoNum = parseFloat(valorLiquido.replace(/\./g, '').replace(',', '.')) || 0;
  const brutoAutoNum = liquidoNum / 0.89;
  const cpAutoNum = brutoAutoNum * 0.11;
  const irrfAutoNum = 0;

  // Valores Finais (Manual ou Auto)
  const finalBruto = valorBrutoManual !== null ? parseFloat(valorBrutoManual.replace(',', '.')) || 0 : brutoAutoNum;
  const finalCP = valorCPManual !== null ? parseFloat(valorCPManual.replace(',', '.')) || 0 : cpAutoNum;
  const finalIRRF = valorIRRFManual !== null ? parseFloat(valorIRRFManual.replace(',', '.')) || 0 : irrfAutoNum;
  
  const mesReferenciaString = `${monthNames[selecaoMes - 1]}/${selecaoAno}`;
  const autoDescricao = `Desenvolvimento de soluções tecnológicas e consultoria em gestão empresarial na empresa ${clientData?.razaoSocial || '[RAZÃO SOCIAL]'}. Referente ao mês de ${mesReferenciaString}. Valor líquido acordado: ${formatCurrency(liquidoNum)}.`;
  const finalDescricao = descricaoManual !== null ? descricaoManual : autoDescricao;

  const runRobot = async () => {
    setIsRobotRunning(true);
    try {
        // Prepare data for the robot
        const robotData = {
            data_competencia: dataCompetencia,
            cnpj_tomador: cleanCnpj(clientData?.cnpj || cnpj),
            descricao: finalDescricao,
            valor_bruto: finalBruto.toFixed(2).replace('.', ','),
            valor_irrf: finalIRRF.toFixed(2).replace('.', ','),
            valor_cp: finalCP.toFixed(2).replace('.', ','),
            portal_login: portalLogin,
            portal_senha: portalSenha
        };

        // Call Local Bridge via Firestore
        await setDoc(doc(db, 'automations', 'hermes_robot'), {
            params: robotData,
            status: 'requested',
            timestamp: new Date().toISOString()
        });

        alert("Comando de Emissão enviado para o Hermes Robot! 🤖\n\nAbra o terminal do sistema e verifique se o 'robot_bridge.py' está rodando.");
    } catch (error) {
        console.error("Erro ao executar robô:", error);
        setIsRobotRunning(false);
    }
  };

  const [robotStatus, setRobotStatus] = useState<string>('idle');

  useEffect(() => {
    const unsub = onSnapshot(doc(db, 'automations', 'hermes_robot'), (docSnap) => {
        const data = docSnap.data();
        if (data) {
            setRobotStatus(data.status);
            if (data.status === 'requested') setIsRobotRunning(true);
            if (data.status === 'error') setIsRobotRunning(false);
        }
    });
    return () => unsub();
  }, []);

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

            <div className="grid grid-cols-6 gap-3">
              <div className="col-span-2">
                <label className="block text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">Competência</label>
                <input 
                  type="text" 
                  value={formatDataCompetenciaDisplay(dataCompetencia)}
                  onChange={handleDataCompetenciaChange}
                  placeholder="DD/MM/AAAA"
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-black text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">Mês Ref.</label>
                <select 
                  value={selecaoMes}
                  onChange={(e) => setSelecaoMes(Number(e.target.value))}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500 appearance-none bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2212%22%20height%3D%2212%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%2394a3b8%22%20stroke-width%3D%223%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M6%209l6%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:14px] bg-[right_12px_center] bg-no-repeat"
                >
                  {monthNames.map((m, i) => (
                    <option key={m} value={i + 1}>{m}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-2">
                <label className="block text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">Ano Ref.</label>
                <input 
                  type="number" 
                  value={selecaoAno}
                  onChange={(e) => setSelecaoAno(Number(e.target.value))}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
            </div>

            <div className="space-y-3">
              <label className="block text-[9px] font-black text-slate-400 uppercase tracking-widest">CNPJ do Tomador</label>
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

            {/* Configurações Avançadas de Tributos */}
            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100 space-y-4">
                <h4 className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Ajuste de Impostos (Opcional)</h4>
                
                <div className="grid grid-cols-3 gap-3">
                    <div>
                        <label className="block text-[8px] font-bold text-slate-400 uppercase mb-1">Bruto (Override)</label>
                        <input 
                            type="text" 
                            placeholder={brutoAutoNum.toFixed(2).replace('.', ',')}
                            value={valorBrutoManual || ''}
                            onChange={(e) => setValorBrutoManual(e.target.value)}
                            className="w-full bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs font-bold text-slate-700 outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                    </div>
                    <div>
                        <label className="block text-[8px] font-bold text-slate-400 uppercase mb-1">CP/INSS (Override)</label>
                        <input 
                            type="text" 
                            placeholder={cpAutoNum.toFixed(2).replace('.', ',')}
                            value={valorCPManual || ''}
                            onChange={(e) => setValorCPManual(e.target.value)}
                            className="w-full bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs font-bold text-slate-700 outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                    </div>
                    <div>
                        <label className="block text-[8px] font-bold text-slate-400 uppercase mb-1">IRRF (Override)</label>
                        <input 
                            type="text" 
                            placeholder="0,00"
                            value={valorIRRFManual || ''}
                            onChange={(e) => setValorIRRFManual(e.target.value)}
                            className="w-full bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs font-bold text-slate-700 outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                    </div>
                </div>

                <div>
                    <label className="block text-[8px] font-bold text-slate-400 uppercase mb-1">Descrição Manual</label>
                    <textarea 
                        value={finalDescricao}
                        onChange={(e) => setDescricaoManual(e.target.value)}
                        className="w-full bg-white border border-slate-200 rounded-lg px-3 py-2 text-[10px] font-semibold text-slate-600 outline-none focus:ring-2 focus:ring-emerald-500 min-h-[60px]"
                    />
                </div>
            </div>

            {/* Acesso ao Portal (Login Automático) */}
            <div className="bg-slate-900 rounded-2xl p-5 border border-slate-800 space-y-4 shadow-xl">
                <div className="flex items-center gap-2 mb-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
                    <h4 className="text-[10px] font-black text-emerald-400 uppercase tracking-widest">Acesso ao Portal (Auto-Login)</h4>
                </div>
                
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-[8px] font-bold text-slate-400 uppercase mb-1">CPF/CNPJ</label>
                        <input 
                            type="text" 
                            value={portalLogin}
                            onChange={(e) => setPortalLogin(e.target.value)}
                            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs font-bold text-white outline-none focus:ring-2 focus:ring-emerald-500 placeholder:text-slate-600"
                            placeholder="Usuario"
                        />
                    </div>
                    <div>
                        <label className="block text-[8px] font-bold text-slate-400 uppercase mb-1">Senha</label>
                        <input 
                            type="password" 
                            value={portalSenha}
                            onChange={(e) => setPortalSenha(e.target.value)}
                            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs font-bold text-white outline-none focus:ring-2 focus:ring-emerald-500 placeholder:text-slate-600"
                            placeholder="••••••••"
                        />
                    </div>
                </div>
                <p className="text-[8px] text-slate-500 leading-tight italic">
                    Dados são processados localmente pelo robô e não ficam armazenados permanentemente.
                </p>
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
              disabled={!valorLiquido}
              className="w-full bg-emerald-950 text-white py-4 rounded-xl font-black text-xs uppercase tracking-widest mt-4 hover:bg-emerald-900 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg"
            >
              Visualizar Dados NFS-e
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
                                onClick={() => handleCopy(finalDescricao, 'descricao')}
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
                            {finalDescricao}
                        </p>
                    </div>

                    {/* Valores Críticos */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-emerald-50 p-5 rounded-xl border border-emerald-200 relative overflow-hidden group">
                            <span className="block text-[9px] font-black text-emerald-700 uppercase tracking-widest mb-1">Valor Bruto (Serviço)</span>
                            <div className="text-2xl font-black text-emerald-900">{formatCurrency(finalBruto)}</div>
                            <button 
                                onClick={() => handleCopy(finalBruto.toFixed(2).replace('.', ','), 'bruto')}
                                className="absolute top-4 right-4 p-2 bg-white/80 rounded-lg text-emerald-600 opacity-0 group-hover:opacity-100 hover:bg-white transition-all shadow-sm"
                            >
                                {copiedField === 'bruto' ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>}
                            </button>
                        </div>

                        <div className="bg-rose-50 p-5 rounded-xl border border-rose-200 relative overflow-hidden group">
                            <span className="block text-[9px] font-black text-rose-700 uppercase tracking-widest mb-1">INSS / CP Retida (11%)</span>
                            <div className="text-2xl font-black text-rose-900">{formatCurrency(finalCP)}</div>
                            <button 
                                onClick={() => handleCopy(finalCP.toFixed(2).replace('.', ','), 'cp')}
                                className="absolute top-4 right-4 p-2 bg-white/80 rounded-lg text-rose-600 opacity-0 group-hover:opacity-100 hover:bg-white transition-all shadow-sm"
                            >
                                {copiedField === 'cp' ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>}
                            </button>
                        </div>
                    </div>

                    {/* Botão de Ação do Robô */}
                    <div className="pt-2 flex flex-col gap-3">
                        {robotStatus === 'processing' && isRobotRunning && (
                          <button
                            onClick={async () => {
                              await setDoc(doc(db, 'automations', 'hermes_robot'), { status: 'login_confirmed' }, { merge: true });
                            }}
                            className="w-full py-4 bg-emerald-100 text-emerald-700 rounded-xl font-bold text-xs uppercase tracking-widest hover:bg-emerald-200 transition-all flex items-center justify-center gap-2 border border-emerald-200 animate-pulse shadow-sm"
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                            Já estou Logado! Prosseguir Preenchimento
                          </button>
                        )}
                        
                        <button
                            onClick={runRobot}
                            disabled={isRobotRunning && (robotStatus === 'requested' || robotStatus === 'processing')}
                            className={`w-full py-5 rounded-[1.5rem] font-black uppercase tracking-widest text-sm flex items-center justify-center gap-3 transition-all transform hover:scale-[1.02] active:scale-95 shadow-xl ${
                                (isRobotRunning && (robotStatus === 'requested' || robotStatus === 'processing'))
                                ? 'bg-slate-200 text-slate-500 cursor-not-allowed' 
                                : 'bg-gradient-to-r from-emerald-600 to-teal-700 text-white hover:from-emerald-500 hover:to-teal-600 active:from-emerald-700 active:to-teal-800'
                            }`}
                        >
                            {(isRobotRunning && (robotStatus === 'requested' || robotStatus === 'processing')) ? (
                                <>
                                    <span className="w-5 h-5 border-3 border-emerald-500 border-t-emerald-100 rounded-full animate-spin"></span>
                                    {robotStatus === 'requested' ? 'Chamando Robô...' : 'Robô em Ação...'}
                                </>
                            ) : (
                                <>
                                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
                                    Emitir NFS-e com Robô
                                </>
                            )}
                        </button>
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
