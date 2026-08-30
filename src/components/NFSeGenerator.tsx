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

  // O painel de saida aparece assim que ha um valor liquido, que e o que o
  // estado vazio ja promete ("preencha os parametros de entrada").
  //
  // Antes disto era um `useState(false)` cujo `setShowResults` NUNCA era
  // chamado: o painel inteiro — CNPJ, codigo 17.01, bruto, INSS e os botoes de
  // copiar — era inalcancavel, e a tela ficava permanentemente em
  // WAITING_FOR_DATA_STREAM. A regressao entrou junto com a remocao do botao
  // "gerar", quando o calculo passou a ser ao vivo, e ninguem viu porque o
  // teste deste componente existia e nao rodava: o `npm test` enumerava os
  // arquivos um a um e este nao estava na lista.
  const showResults = liquidoNum > 0;

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
    <div className="fixed inset-0 bg-on-surface/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-surface rounded-lg border-2 border-primary-tactile shadow-none w-full max-w-5xl max-h-[95vh] overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
        
        {/* Header Industrial */}
        <div className="bg-on-surface text-surface p-6 flex justify-between items-center border-b border-primary-tactile shrink-0">
          <div>
            <h2 className="text-2xl font-sans font-semibold text-white tracking-tight">NFSe_Data_Generator_V1</h2>
            <div className="flex items-center gap-3 mt-1">
                <span className="text-[10px] font-sans font-semibold uppercase tracking-[0.2em] opacity-50">// NATIONAL_PORTAL_INTEGRATION</span>
                <span className="w-1 h-1 rounded-full bg-primary-tactile"></span>
                <span className="text-[10px] font-sans font-semibold uppercase tracking-[0.2em] opacity-50">STATUS: SYSTEM_READY</span>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="w-10 h-10 border border-white/20 bg-white/5 hover:bg-white/10 flex items-center justify-center transition-colors rounded-soft-touch"
          >
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="p-0 flex-1 overflow-hidden flex">
          <div className="w-full h-full grid md:grid-cols-5 overflow-hidden">
          {/* Coluna Esquerda: Formulário */}
          <div className="md:col-span-2 p-8 border-r border-[#e5e7eb] dark:border-white/10 overflow-y-auto space-y-8 bg-surface">
            <div>
              <h3 className="text-[10px] font-sans font-semibold uppercase text-primary-tactile tracking-[0.3em] mb-6 flex items-center gap-2">
                  <span className="w-2 h-2 bg-primary-tactile"></span>
                  INPUT_DATA_STREAM
              </h3>
              
              <div className="space-y-6">
                <div>
                  <label className="block text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest mb-2">NET_AMOUNT_RECEIVABLE (BRL)</label>
                  <input 
                    type="text" 
                    value={valorLiquido}
                    onChange={(e) => setValorLiquido(e.target.value)}
                    placeholder="0000,00"
                    className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch px-4 py-3 text-sm font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                  />
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div className="col-span-1">
                    <label className="block text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest mb-2">COMPETENCE</label>
                    <input 
                      type="text" 
                      value={formatDataCompetenciaDisplay(dataCompetencia)}
                      onChange={handleDataCompetenciaChange}
                      placeholder="DDMMYYYY"
                      className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                    />
                  </div>
                  <div className="col-span-1">
                    <label className="block text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest mb-2">REF_MONTH</label>
                    <select 
                      value={selecaoMes}
                      onChange={(e) => setSelecaoMes(Number(e.target.value))}
                      className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch px-3 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile appearance-none"
                    >
                      {monthNames.map((m, i) => (
                        <option key={m} value={i + 1}>{m.toUpperCase()}</option>
                      ))}
                    </select>
                  </div>
                  <div className="col-span-1">
                    <label className="block text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest mb-2">REF_YEAR</label>
                    <input 
                      type="number" 
                      value={selecaoAno}
                      onChange={(e) => setSelecaoAno(Number(e.target.value))}
                      className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest mb-2">TAKER_TAX_ID (CNPJ)</label>
                  <div className="flex gap-2">
                    <input 
                      type="text" 
                      value={formatCnpj(cnpj)}
                      onChange={(e) => setCnpj(e.target.value)}
                      placeholder="00.000.000/0000-00"
                      maxLength={18}
                      className="flex-1 bg-white border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch px-4 py-3 text-sm font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                    />
                    <button 
                      onClick={buscarCnpj}
                      disabled={loading || cleanCnpj(cnpj).length !== 14}
                      className="bg-primary-tactile text-white px-4 rounded-soft-touch font-sans font-semibold text-[10px] uppercase tracking-widest disabled:opacity-50 hover:bg-on-surface transition-all flex items-center justify-center min-w-[50px]"
                    >
                      {loading ? (
                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                      ) : (
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Configurações Avançadas de Tributos */}
            <div className="bg-slate-50 rounded-lg p-6 border border-[#e5e7eb] dark:border-white/10 space-y-6">
                <h4 className="text-[8px] font-sans font-semibold text-primary-tactile uppercase tracking-widest">// TAX_OVERRIDE_INTERFACE</h4>
                
                <div className="grid grid-cols-3 gap-3">
                    <div>
                        <label className="block text-[7px] font-sans font-semibold text-slate-400 uppercase mb-1">BRUTO_OVR</label>
                        <input 
                            type="text" 
                            placeholder={brutoAutoNum.toFixed(2).replace('.', ',')}
                            value={valorBrutoManual || ''}
                            onChange={(e) => setValorBrutoManual(e.target.value)}
                            className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg px-3 py-2 text-[10px] font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                        />
                    </div>
                    <div>
                        <label className="block text-[7px] font-sans font-semibold text-slate-400 uppercase mb-1">CP_INSS_OVR</label>
                        <input 
                            type="text" 
                            placeholder={cpAutoNum.toFixed(2).replace('.', ',')}
                            value={valorCPManual || ''}
                            onChange={(e) => setValorCPManual(e.target.value)}
                            className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg px-3 py-2 text-[10px] font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                        />
                    </div>
                    <div>
                        <label className="block text-[7px] font-sans font-semibold text-slate-400 uppercase mb-1">IRRF_OVR</label>
                        <input 
                            type="text" 
                            placeholder="0,00"
                            value={valorIRRFManual || ''}
                            onChange={(e) => setValorIRRFManual(e.target.value)}
                            className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg px-3 py-2 text-[10px] font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                        />
                    </div>
                </div>

                <div>
                    <label className="block text-[7px] font-sans font-semibold text-slate-400 uppercase mb-1">MANUAL_DESCRIPTION_INJECTION</label>
                    <textarea 
                        value={finalDescricao}
                        onChange={(e) => setDescricaoManual(e.target.value)}
                        className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg px-3 py-2 text-[10px] font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile min-h-[80px] resize-none"
                    />
                </div>
            </div>

            {/* Acesso ao Portal (Login Automático) */}
            <div className="bg-on-surface rounded-lg p-6 text-white space-y-6">
                <div className="flex items-center gap-2 mb-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
                    <h4 className="text-[8px] font-sans font-semibold text-emerald-400 uppercase tracking-widest">// AUTO_LOGIN_ACCESS_RESOURCES</h4>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-[7px] font-sans font-semibold text-white/40 uppercase mb-1">ACCESS_ID</label>
                        <input 
                            type="text" 
                            value={portalLogin}
                            onChange={(e) => setPortalLogin(e.target.value)}
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-[10px] font-sans font-semibold text-white outline-none focus:ring-1 focus:ring-emerald-500"
                            placeholder="USER_IDENTIFIER"
                        />
                    </div>
                    <div>
                        <label className="block text-[7px] font-sans font-semibold text-white/40 uppercase mb-1">SECURE_TOKEN</label>
                        <input 
                            type="password" 
                            value={portalSenha}
                            onChange={(e) => setPortalSenha(e.target.value)}
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-[10px] font-sans font-semibold text-white outline-none focus:ring-1 focus:ring-emerald-500"
                            placeholder="********"
                        />
                    </div>
                </div>
                <p className="text-[7px] font-sans font-semibold text-white/30 leading-relaxed uppercase tracking-widest">
                    PRIVACY_NOTICE: SENSITIVE_DATA_PROCESSED_LOCALLY_BY_BRIDGE. NO_PERSISTENT_STORAGE_DETECTED.
                </p>
            </div>
          </div>

          {/* Coluna Direita: Resultados */}
          <div className="md:col-span-3 bg-slate-50 p-8 overflow-y-auto relative bg-[url('https://www.transparenttextures.com/patterns/graphy.png')]">
            {!showResults ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-300 p-12 text-center">
                <div className="w-20 h-20 border-2 border-dashed border-slate-200 flex items-center justify-center mb-6">
                    <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                </div>
                <h4 className="font-sans font-semibold text-[10px] uppercase tracking-[0.2em]">WAITING_FOR_DATA_STREAM</h4>
                <p className="font-sans text-[8px] uppercase tracking-widest mt-2">INITIALIZE_PROCEDURE_BY_FILLING_INPUT_PARAMETERS</p>
              </div>
            ) : (
              <div className="space-y-8 animate-in slide-in-from-right-4 duration-300">
                
                {/* Copiar Block Helper */}
                <div className="flex items-center gap-3 bg-white p-4 border border-[#e5e7eb] dark:border-white/10 border-l-4 border-l-emerald-500">
                    <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                    <span className="text-[10px] font-sans font-semibold uppercase tracking-widest text-on-surface">GENERATED_MIRROR_STREAM // READY_FOR_TRANSFER</span>
                </div>

                <div className="space-y-6">
                    {/* Linha 1: Códigos */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-white p-6 rounded-lg border border-[#e5e7eb] dark:border-white/10 shadow-none">
                            <span className="block text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest mb-2">TAKER_ID (CNPJ)</span>
                            <div className="flex justify-between items-center">
                                <span className="text-sm font-sans font-semibold text-on-surface">{clientData?.cnpj || cnpj}</span>
                                <button 
                                    onClick={() => handleCopy(cleanCnpj(clientData?.cnpj || cnpj), 'cnpj')}
                                    className={`p-2 rounded-soft-touch transition-all ${copiedField === 'cnpj' ? 'bg-emerald-500 text-white' : 'bg-slate-100 hover:bg-on-surface hover:text-white text-slate-500'}`}
                                >
                                    {copiedField === 'cnpj' ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>}
                                </button>
                            </div>
                        </div>

                        <div className="bg-white p-6 rounded-lg border border-[#e5e7eb] dark:border-white/10 shadow-none">
                            <span className="block text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest mb-2">TAX_CLASSIFICATION_CODE</span>
                            <div className="flex justify-between items-center">
                                <span className="text-sm font-sans font-semibold text-on-surface">17.01</span>
                                <button 
                                    onClick={() => handleCopy('17.01', 'codigo')}
                                    className={`p-2 rounded-soft-touch transition-all ${copiedField === 'codigo' ? 'bg-emerald-500 text-white' : 'bg-slate-100 hover:bg-on-surface hover:text-white text-slate-500'}`}
                                >
                                    {copiedField === 'codigo' ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>}
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* Descrição do Serviço */}
                    <div className="bg-white p-6 rounded-lg border border-[#e5e7eb] dark:border-white/10 shadow-none">
                        <div className="flex justify-between items-start mb-4">
                            <span className="block text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest">SERVICE_DESCRIPTION_BLOCK</span>
                            <button 
                                onClick={() => handleCopy(finalDescricao, 'descricao')}
                                className={`flex items-center gap-2 px-4 py-2 rounded-soft-touch text-[9px] font-sans font-semibold uppercase tracking-widest transition-all ${copiedField === 'descricao' ? 'bg-emerald-500 text-white' : 'bg-on-surface text-white hover:bg-primary-tactile'}`}
                            >
                                {copiedField === 'descricao' ? (
                                    <><svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> COPIED!</>
                                ) : (
                                    <><svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg> COPY_STREAM</>
                                )}
                            </button>
                        </div>
                        <p className="text-[11px] font-sans font-semibold text-on-surface leading-relaxed bg-slate-50 p-4 border border-[#e5e7eb] dark:border-white/10 border-dashed">
                            {finalDescricao}
                        </p>
                    </div>

                    {/* Valores Críticos */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-surface p-6 rounded-lg border border-[#e5e7eb] dark:border-white/10 border-l-4 border-l-primary-tactile relative overflow-hidden group">
                            <span className="block text-[8px] font-sans font-semibold text-primary-tactile uppercase tracking-widest mb-2">GROSS_SERVICE_AMOUNT</span>
                            <div className="text-2xl font-sans font-semibold text-on-surface">{formatCurrency(finalBruto)}</div>
                            <button 
                                onClick={() => handleCopy(finalBruto.toFixed(2).replace('.', ','), 'bruto')}
                                className="absolute top-4 right-4 p-2 bg-on-surface rounded-soft-touch text-white opacity-0 group-hover:opacity-100 hover:bg-primary-tactile transition-all"
                            >
                                {copiedField === 'bruto' ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>}
                            </button>
                        </div>

                        <div className="bg-surface p-6 rounded-lg border border-[#e5e7eb] dark:border-white/10 border-l-4 border-l-accent-tactile relative overflow-hidden group">
                            <span className="block text-[8px] font-sans font-semibold text-accent-tactile uppercase tracking-widest mb-2">INSS_CP_RETAINED (11%)</span>
                            <div className="text-2xl font-sans font-semibold text-on-surface">{formatCurrency(finalCP)}</div>
                            <button 
                                onClick={() => handleCopy(finalCP.toFixed(2).replace('.', ','), 'cp')}
                                className="absolute top-4 right-4 p-2 bg-on-surface rounded-soft-touch text-white opacity-0 group-hover:opacity-100 hover:bg-accent-tactile transition-all"
                            >
                                {copiedField === 'cp' ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>}
                            </button>
                        </div>
                    </div>

                    {/* Botão de Ação do Robô */}
                    <div className="pt-2 flex flex-col gap-4">
                        {robotStatus === 'processing' && isRobotRunning && (
                          <button
                            onClick={async () => {
                              await setDoc(doc(db, 'automations', 'hermes_robot'), { status: 'login_confirmed' }, { merge: true });
                            }}
                            className="w-full py-4 bg-emerald-50 text-emerald-700 rounded-lg border border-emerald-200 font-sans font-semibold text-[10px] uppercase tracking-[0.2em] hover:bg-emerald-100 transition-all flex items-center justify-center gap-3 animate-pulse"
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                            AUTH_TOKEN_SIGNALED // PROCEED_TO_FILL
                          </button>
                        )}
                        
                        <button
                            onClick={runRobot}
                            disabled={isRobotRunning && (robotStatus === 'requested' || robotStatus === 'processing')}
                            className={`w-full py-5 rounded-lg font-sans font-semibold uppercase tracking-[0.3em] text-xs flex items-center justify-center gap-4 transition-all shadow-none border-2 ${
                                (isRobotRunning && (robotStatus === 'requested' || robotStatus === 'processing'))
                                ? 'bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed' 
                                : 'bg-on-surface text-surface border-on-surface hover:bg-primary-tactile hover:border-primary-tactile active:scale-[0.98]'
                            }`}
                        >
                            {(isRobotRunning && (robotStatus === 'requested' || robotStatus === 'processing')) ? (
                                <>
                                    <span className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin"></span>
                                    {robotStatus === 'requested' ? 'SIGNAL_DISPATCHED...' : 'ROBOT_ENGAGED...'}
                                </>
                            ) : (
                                <>
                                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
                                    EXECUTE_ROBOTIC_EMISSION_V1
                                </>
                            )}
                        </button>
                    </div>

                    {/* Outros Impostos Zerados */}
                    <div className="bg-white p-6 rounded-lg border border-[#e5e7eb] dark:border-white/10 border-dashed">
                        <span className="block text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest mb-4 text-center">// SECONDARY_TAX_STREAMS (NULL_VALS)</span>
                        <div className="grid grid-cols-5 gap-3">
                           {['ISS', 'PIS', 'COFINS', 'CSLL', 'IR'].map(imposto => (
                               <div key={imposto} className="text-center group border-r border-[#e5e7eb] dark:border-white/10 last:border-0">
                                   <div className="text-[8px] font-sans font-semibold text-slate-500 uppercase">{imposto}</div>
                                   <div className="text-[10px] font-sans font-semibold text-slate-300 mt-2 cursor-pointer hover:text-primary-tactile transition-colors" onClick={() => handleCopy('0,00', `imposto_${imposto}`)}>0,00</div>
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
    </div>
  );
};
