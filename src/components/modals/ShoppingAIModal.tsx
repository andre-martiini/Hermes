import React, { useState, useRef, useEffect } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '@/firebase';
import type { TranscriptionResponse, ShoppingItem } from '../../../types';

interface AIMatchedItem {
  id: string;
  nome: string;
  categoria: string;
  quantidade: string;
  unit: string;
  confirmed: boolean;
  isNew: boolean;
}

interface ShoppingAIModalProps {
  isOpen: boolean;
  onClose: () => void;
  catalogItems: ShoppingItem[];
  onConfirmItems: (items: { id: string; quantidade: string }[]) => void;
  onViewList: () => void;
}

export const ShoppingAIModal = ({
  isOpen, onClose, catalogItems, onConfirmItems, onViewList,
}: ShoppingAIModalProps) => {
  const [step, setStep] = useState<'input' | 'processing' | 'validation'>('input');
  const [textInput, setTextInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [matchedItems, setMatchedItems] = useState<AIMatchedItem[]>([]);
  const [errorMsg, setErrorMsg] = useState('');
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const resetToInput = () => { setStep('input'); setMatchedItems([]); setErrorMsg(''); };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
    };
  }, []);

  if (!isOpen) return null;

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      audioChunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mr.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/m4a' });
        stream.getTracks().forEach(t => t.stop());
        setStep('processing');
        try {
          const reader = new FileReader();
          reader.readAsDataURL(blob);
          reader.onloadend = async () => {
            try {
              const base64 = (reader.result as string).split(',')[1];
              const fn = httpsCallable(functions, 'transcreverAudio');
              const res = await fn({
                audioBase64: base64,
                sourceRef: { kind: 'unknown', label: 'shopping_voice_capture' },
              });
              const data = res.data as TranscriptionResponse;
              const transcript = data.refined || '';
              if (transcript) {
                await processWithGemini(transcript);
              } else {
                setErrorMsg('Não consegui transcrever o áudio. Tente digitar.');
                setStep('input');
              }
            } catch {
              setErrorMsg('Erro ao transcrever áudio.');
              setStep('input');
            }
          };
        } catch {
          setErrorMsg('Erro ao ler áudio.');
          setStep('input');
        }
      };
      streamRef.current = stream;
      mr.start();
      setIsRecording(true);
    } catch {
      alert('Permissão de microfone negada.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const processWithGemini = async (text: string) => {
    setStep('processing');
    setErrorMsg('');
    try {
      const fn = httpsCallable(functions, 'matchShoppingItemsAI');
      const result = await fn({
        text,
        catalogItems: catalogItems.map((item) => ({
          id: item.id,
          nome: item.nome,
          categoria: item.categoria,
        })),
      });
      const parsed = result.data as { itens?: any[] };

      const resolved: AIMatchedItem[] = (parsed.itens || []).map((it: any) => {
        const catalogItem = it.catalogId ? catalogItems.find(c => c.id === it.catalogId) : null;
        return {
          id: catalogItem?.id || `new_${Date.now()}_${Math.random()}`,
          nome: it.nomeExibido || catalogItem?.nome || 'Item desconhecido',
          categoria: catalogItem?.categoria || 'Geral',
          quantidade: String(it.quantidade || '1'),
          unit: it.unit || 'un',
          confirmed: true,
          isNew: !!it.isNew || !catalogItem,
        };
      });

      if (resolved.length === 0) {
        setErrorMsg('Não identifiquei itens no pedido. Tente descrever de forma diferente.');
        setStep('input');
        return;
      }

      setMatchedItems(resolved);
      setStep('validation');
    } catch (e) {
      console.error(e);
      setErrorMsg('Erro ao processar com IA. Verifique a conexão.');
      setStep('input');
    }
  };

  const handleSubmitText = async () => {
    if (!textInput.trim()) return;
    await processWithGemini(textInput.trim());
  };

  const toggleItem = (id: string) => {
    setMatchedItems(prev => prev.map(i => i.id === id ? { ...i, confirmed: !i.confirmed } : i));
  };

  const updateQtd = (id: string, val: string) => {
    setMatchedItems(prev => prev.map(i => i.id === id ? { ...i, quantidade: val } : i));
  };

  const handleConfirm = () => {
    const toAdd = matchedItems.filter(i => i.confirmed && !i.isNew);
    if (toAdd.length === 0) { onClose(); return; }
    onConfirmItems(toAdd.map(i => ({ id: i.id, quantidade: i.quantidade })));
    setTextInput('');
    setMatchedItems([]);
    setStep('input');
    onClose();
  };

  const confirmedCount = matchedItems.filter(i => i.confirmed && !i.isNew).length;
  const newCount = matchedItems.filter(i => i.isNew).length;

  return (
    <div className="fixed inset-0 z-[250] flex items-center justify-center p-0 md:p-4 bg-slate-900/70 backdrop-blur-md animate-in fade-in">
      <div className="bg-white w-full max-w-2xl h-full md:h-auto md:max-h-[92vh] rounded-none md:rounded-[2.5rem] shadow-[0_40px_80px_-20px_rgba(0,0,0,0.35)] flex flex-col overflow-hidden animate-in zoom-in-95 duration-300">

        {/* Header */}
        <div className="p-7 md:p-8 border-b border-slate-100 bg-gradient-to-br from-emerald-50/80 to-white flex items-center gap-4 flex-shrink-0">
          <div className="w-12 h-12 bg-emerald-600 rounded-2xl flex items-center justify-center shadow-lg shadow-emerald-200 flex-shrink-0">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-xl font-black text-slate-900 tracking-tight">Assistente de Compras IA</h3>
            <p className="text-emerald-600 text-[10px] font-black uppercase tracking-[0.2em] mt-0.5">
              {step === 'input' ? 'Diga o que você quer comprar' : step === 'processing' ? 'Buscando no catálogo...' : 'Valide os itens identificados'}
            </p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-2xl transition-all flex-shrink-0">
            <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-7 md:p-8 space-y-5">

          {step === 'input' && (
            <>
              {errorMsg && (
                <div className="bg-rose-50 border border-rose-100 rounded-2xl px-5 py-3 flex items-center gap-3">
                  <svg className="w-4 h-4 text-rose-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                  <p className="text-rose-700 text-sm font-bold">{errorMsg}</p>
                </div>
              )}

              <div className="bg-slate-50 rounded-[2rem] border-2 border-slate-100 focus-within:border-emerald-400 transition-all shadow-inner overflow-hidden">
                <div className="flex items-start gap-3 p-4">
                  <button
                    onClick={isRecording ? stopRecording : startRecording}
                    className={`mt-1 w-12 h-12 rounded-2xl flex items-center justify-center flex-shrink-0 transition-all ${isRecording ? 'bg-rose-500 text-white animate-pulse shadow-lg shadow-rose-200' : 'bg-white border border-slate-200 text-slate-400 hover:text-emerald-600 hover:border-emerald-200 hover:shadow-md'}`}
                    title={isRecording ? 'Parar gravação' : 'Gravar áudio'}
                  >
                    {isRecording
                      ? <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
                      : <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>}
                  </button>
                  <textarea
                    autoFocus
                    className="flex-1 bg-transparent border-none outline-none py-3 text-base font-bold text-slate-800 placeholder:text-slate-300 resize-none min-h-[120px]"
                    placeholder={isRecording ? 'Gravando... Fale os itens que deseja comprar...' : 'Ex: "2 kg de arroz, 1 caixa de leite, ricota, sabão em pó e 3 iogurtes"'}
                    value={textInput}
                    disabled={isRecording}
                    onChange={e => setTextInput(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) handleSubmitText(); }}
                  />
                </div>
                {isRecording && (
                  <div className="px-5 pb-4 flex items-center gap-2">
                    <div className="flex gap-0.5">
                      {[...Array(8)].map((_, i) => (
                        <div key={i} className="w-1 bg-rose-500 rounded-full animate-pulse" style={{ height: `${8 + Math.random() * 16}px`, animationDelay: `${i * 100}ms` }} />
                      ))}
                    </div>
                    <span className="text-rose-600 text-[11px] font-black uppercase tracking-widest">Gravando</span>
                  </div>
                )}
              </div>

              <div className="bg-emerald-50/60 rounded-2xl border border-emerald-100/60 px-5 py-4 flex gap-3">
                <svg className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                <p className="text-[11px] font-bold text-emerald-800 leading-relaxed">
                  O Hermes vai buscar os itens no seu catálogo usando IA. "Ricota" pode corresponder a "Queijo Ricota", "Bombril" a "Palha de Aço", etc.
                </p>
              </div>
            </>
          )}

          {step === 'processing' && (
            <div className="py-20 flex flex-col items-center justify-center gap-6 text-center">
              <div className="relative w-20 h-20">
                <div className="w-20 h-20 rounded-full border-4 border-emerald-100 animate-spin border-t-emerald-500" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <svg className="w-8 h-8 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                </div>
              </div>
              <div>
                <p className="font-black text-slate-800 text-lg">Hermes está pensando...</p>
                <p className="text-slate-400 text-sm font-medium mt-1">Buscando correspondências no catálogo</p>
              </div>
            </div>
          )}

          {step === 'validation' && (
            <div className="space-y-4 animate-in fade-in duration-300">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-black text-slate-800">{matchedItems.filter(i => !i.isNew).length} itens identificados</p>
                  {newCount > 0 && <p className="text-[10px] text-amber-600 font-black uppercase tracking-widest mt-0.5">{newCount} não encontrado{newCount > 1 ? 's' : ''} no catálogo</p>}
                </div>
                <button onClick={resetToInput} className="text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-slate-700 transition-colors">
                  ↺ Refazer
                </button>
              </div>

              <div className="space-y-2">
                {matchedItems.map(item => (
                  <div
                    key={item.id}
                    onClick={() => !item.isNew && toggleItem(item.id)}
                    className={`rounded-2xl border px-5 py-4 flex items-center gap-4 transition-all ${item.isNew ? 'bg-amber-50/50 border-amber-100 opacity-60 cursor-not-allowed' : item.confirmed ? 'bg-emerald-50/40 border-emerald-200 cursor-pointer hover:bg-emerald-50' : 'bg-slate-50 border-slate-100 cursor-pointer opacity-50 hover:opacity-70'}`}
                  >
                    <div className={`w-7 h-7 rounded-xl border-2 flex items-center justify-center flex-shrink-0 transition-all ${item.isNew ? 'border-amber-300 bg-amber-100' : item.confirmed ? 'bg-emerald-500 border-emerald-500 text-white' : 'border-slate-300 bg-white'}`}>
                      {item.isNew
                        ? <svg className="w-3.5 h-3.5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01" /></svg>
                        : item.confirmed ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                          : null}
                    </div>

                    <div className="flex-1 min-w-0">
                      <p className={`font-black text-sm truncate ${item.isNew ? 'text-amber-700' : 'text-slate-900'}`}>{item.nome}</p>
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">
                        {item.isNew ? '? Não no catálogo' : item.categoria}
                      </p>
                    </div>

                    {!item.isNew && (
                      <div onClick={e => e.stopPropagation()} className="flex items-center gap-2 bg-white border border-slate-100 rounded-xl px-3 py-2 shadow-sm">
                        <button onClick={() => updateQtd(item.id, String(Math.max(0.5, parseFloat(item.quantidade) - 1)))} className="w-5 h-5 rounded-lg bg-slate-100 font-black flex items-center justify-center text-slate-600 hover:bg-emerald-100 transition-all text-sm leading-none">-</button>
                        <span className="w-12 text-center font-black text-slate-800 text-sm">
                          {item.quantidade} <span className="text-slate-400 font-medium text-[10px]">{item.unit}</span>
                        </span>
                        <button onClick={() => updateQtd(item.id, String(parseFloat(item.quantidade) + 1))} className="w-5 h-5 rounded-lg bg-slate-100 font-black flex items-center justify-center text-slate-600 hover:bg-emerald-100 transition-all text-sm leading-none">+</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {newCount > 0 && (
                <div className="bg-amber-50 border border-amber-100 rounded-2xl px-5 py-3 flex gap-3">
                  <svg className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                  <p className="text-[11px] font-bold text-amber-800 leading-relaxed">
                    {newCount} item(ns) não foram encontrados no catálogo. Cadastre-os primeiro na aba "Cadastro" e o assistente os reconhecerá na próxima vez.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex-shrink-0 p-6 md:p-8 pt-0 space-y-3">
          {step === 'input' && (
            <div className="flex gap-4">
              <button onClick={onClose} className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-2xl transition-all">Fechar</button>
              <button
                onClick={handleSubmitText}
                disabled={!textInput.trim() || isRecording}
                className="flex-[2] bg-emerald-600 text-white py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg shadow-emerald-100 hover:bg-emerald-700 transition-all disabled:opacity-50 disabled:grayscale flex items-center justify-center gap-2 active:scale-[0.98]"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                Processar com IA
              </button>
            </div>
          )}

          {step === 'validation' && (
            <div className="flex gap-4">
              <button onClick={resetToInput} className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-2xl transition-all">Voltar</button>
              <button
                onClick={handleConfirm}
                disabled={confirmedCount === 0}
                className="flex-[2] bg-slate-900 text-white py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-xl hover:bg-emerald-600 transition-all disabled:opacity-50 disabled:grayscale flex items-center justify-center gap-2 active:scale-[0.98]"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                Confirmar {confirmedCount} iten{confirmedCount !== 1 ? 's' : ''}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
