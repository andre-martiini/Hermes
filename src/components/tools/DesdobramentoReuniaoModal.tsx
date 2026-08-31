// src/components/tools/DesdobramentoReuniaoModal.tsx
// Revisão do desdobramento antes de virar tarefa no Hermes.
//
// Criar tarefa é efeito que sai desta tela e aparece no dia de trabalho de
// alguém. Por isso NADA é criado automaticamente: o modelo propõe, a pessoa
// confere item a item, com o trecho literal da reunião à vista, e só então
// cria. É a mesma regra dos cartões — proposta aceita, nunca aplicada.

import React, { useEffect, useState } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions, db } from '@/firebase';
import { addDoc, collection, doc, updateDoc } from 'firebase/firestore';
import {
  DESDOBRAMENTO_VAZIO,
  interpretarDesdobramento,
  montarPromptDesdobramento,
  transcricaoParaDesdobramento,
  type AcaoReuniao,
  type Desdobramento,
} from '../../utils/desdobramentoReuniao';

interface Props {
  isDark: boolean;
  titulo: string;
  falas: readonly { speaker: string; text: string }[];
  /** Documento da reunião em `reunioes`, quando já foi gravada. */
  firestoreId?: string;
  onClose: () => void;
  showToast?: (msg: string, type: 'success' | 'error' | 'info') => void;
}

const hojeIso = () => new Date().toISOString().slice(0, 10);

export const DesdobramentoReuniaoModal: React.FC<Props> = ({
  isDark,
  titulo,
  falas,
  firestoreId,
  onClose,
  showToast,
}) => {
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [dados, setDados] = useState<Desdobramento>(DESDOBRAMENTO_VAZIO);
  const [decisoesAceitas, setDecisoesAceitas] = useState<Set<number>>(new Set());
  const [acoesAceitas, setAcoesAceitas] = useState<Set<number>>(new Set());
  const [criando, setCriando] = useState(false);
  const [criadas, setCriadas] = useState<number | null>(null);

  const painel = isDark ? 'bg-slate-900 border-white/10' : 'bg-white border-slate-200';
  const campo = isDark
    ? 'bg-slate-950 border-white/10 text-slate-100'
    : 'bg-slate-50 border-slate-200 text-slate-900';
  const titl = isDark ? 'text-slate-100' : 'text-slate-900';
  const suave = isDark ? 'text-slate-400' : 'text-slate-500';

  useEffect(() => {
    let cancelado = false;
    void (async () => {
      try {
        const prompt = montarPromptDesdobramento(titulo, transcricaoParaDesdobramento(falas));
        const ask = httpsCallable(functions, 'askChatbot');
        const resposta = await ask({ prompt });
        if (cancelado) return;
        const bruto = (resposta.data as { result?: string })?.result ?? '';
        const lido = interpretarDesdobramento(bruto);
        setDados(lido);
        // Tudo vem MARCADO: o padrão é aceitar o que passou na conferência do
        // trecho literal, e desmarcar o que não serve — revisar é tirar, não
        // catar. Mas nada é criado sem o clique final.
        setDecisoesAceitas(new Set(lido.decisoes.map((_, i) => i)));
        setAcoesAceitas(new Set(lido.acoes.map((_, i) => i)));
      } catch (e) {
        console.error('Erro ao extrair desdobramento da reunião', e);
        if (!cancelado) setErro('Não deu para ler a reunião agora. A transcrição continua salva — dá para tentar de novo.');
      } finally {
        if (!cancelado) setCarregando(false);
      }
    })();
    return () => {
      cancelado = true;
    };
  }, [titulo, falas]);

  const alternar = (conjunto: Set<number>, setar: (s: Set<number>) => void, i: number) => {
    const novo = new Set(conjunto);
    if (novo.has(i)) novo.delete(i);
    else novo.add(i);
    setar(novo);
  };

  const alterarAcao = (i: number, mudanca: Partial<AcaoReuniao>) =>
    setDados(atual => ({
      ...atual,
      acoes: atual.acoes.map((a, indice) => (indice === i ? { ...a, ...mudanca } : a)),
    }));

  const criar = async () => {
    setCriando(true);
    try {
      const escolhidas = dados.acoes.filter((_, i) => acoesAceitas.has(i));
      const agora = new Date().toISOString();
      for (const acao of escolhidas) {
        const descricao = [
          acao.descricao,
          acao.responsavel ? `Responsável citado na reunião: ${acao.responsavel}.` : '',
          `Origem: reunião "${titulo || 'sem título'}". Trecho: "${acao.trecho}"`,
        ]
          .filter(Boolean)
          .join('\n\n');
        await addDoc(collection(db, 'tarefas'), {
          titulo: acao.titulo,
          descricao,
          status: 'em andamento',
          area_tematica: 'NÃO CLASSIFICADA',
          projeto: 'GERAL',
          contabilizar_meta: true,
          execution_lane: acao.minha ? 'avanco' : 'aguardando_terceiro',
          tags: ['reuniao'],
          data_criacao: agora,
          data_inicio: hojeIso(),
          data_limite: acao.prazo || hojeIso(),
        });
      }

      if (firestoreId) {
        await updateDoc(doc(db, 'reunioes', firestoreId), {
          decisoes: dados.decisoes.filter((_, i) => decisoesAceitas.has(i)),
          desdobradoEm: agora,
        });
      }

      setCriadas(escolhidas.length);
      showToast?.(`${escolhidas.length} ação(ões) criadas a partir da reunião.`, 'success');
    } catch (e) {
      console.error('Erro ao criar ações da reunião', e);
      setErro('Algumas ações podem não ter sido criadas. Confira a lista de tarefas antes de repetir.');
    } finally {
      setCriando(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm">
      <div className={`flex h-full max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border shadow-2xl ${painel}`}>
        <header className={`flex shrink-0 items-center gap-3 border-b p-4 ${isDark ? 'border-white/10' : 'border-slate-200'}`}>
          <div className="min-w-0 flex-1">
            <h2 className={`text-base font-bold ${titl}`}>Desdobramento da reunião</h2>
            <p className={`truncate text-xs ${suave}`}>
              Proposta de leitura. Nada é criado antes de você conferir e clicar.
            </p>
          </div>
          <button onClick={onClose} className={`rounded-xl border px-3 py-2 text-xs font-bold uppercase tracking-wider ${campo}`}>
            Fechar
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {carregando && <p className={`text-sm ${suave}`}>Lendo a reunião…</p>}

          {erro && (
            <p className={`rounded-xl px-3 py-2 text-xs font-semibold ${isDark ? 'bg-rose-500/10 text-rose-300' : 'bg-rose-50 text-rose-700'}`}>
              {erro}
            </p>
          )}

          {!carregando && !erro && dados.decisoes.length === 0 && dados.acoes.length === 0 && (
            <p className={`text-sm leading-relaxed ${suave}`}>
              Esta reunião não produziu decisão nem tarefa que a transcrição sustente. É um
              resultado comum, e não quer dizer que a leitura falhou.
            </p>
          )}

          {dados.decisoes.length > 0 && (
            <section className="mb-4">
              <h3 className={`mb-2 text-[10px] font-bold uppercase tracking-wider ${suave}`}>
                Decisões ({dados.decisoes.length})
              </h3>
              <div className="space-y-2">
                {dados.decisoes.map((d, i) => (
                  <label key={i} className={`flex gap-2 rounded-2xl border p-3 ${campo}`}>
                    <input
                      type="checkbox"
                      checked={decisoesAceitas.has(i)}
                      onChange={() => alternar(decisoesAceitas, setDecisoesAceitas, i)}
                      className="mt-0.5"
                    />
                    <div className="min-w-0 flex-1">
                      <p className={`text-sm font-semibold ${titl}`}>{d.texto}</p>
                      <p className={`mt-1 text-[11px] italic leading-relaxed ${suave}`}>“{d.trecho}”</p>
                    </div>
                  </label>
                ))}
              </div>
            </section>
          )}

          {dados.acoes.length > 0 && (
            <section>
              <h3 className={`mb-2 text-[10px] font-bold uppercase tracking-wider ${suave}`}>
                Ações ({dados.acoes.length})
              </h3>
              <div className="space-y-2">
                {dados.acoes.map((a, i) => (
                  <article key={i} className={`rounded-2xl border p-3 ${campo}`}>
                    <div className="flex gap-2">
                      <input
                        type="checkbox"
                        checked={acoesAceitas.has(i)}
                        onChange={() => alternar(acoesAceitas, setAcoesAceitas, i)}
                        className="mt-2"
                      />
                      <div className="min-w-0 flex-1 space-y-2">
                        <input
                          value={a.titulo}
                          onChange={e => alterarAcao(i, { titulo: e.target.value })}
                          className={`w-full rounded-xl border px-3 py-2 text-sm font-semibold outline-none ${campo}`}
                        />
                        <div className="flex flex-wrap gap-2">
                          <input
                            value={a.responsavel ?? ''}
                            onChange={e => alterarAcao(i, { responsavel: e.target.value })}
                            placeholder="Responsável (opcional)"
                            className={`min-w-0 flex-1 rounded-xl border px-3 py-1.5 text-xs outline-none ${campo}`}
                          />
                          <input
                            type="date"
                            value={a.prazo ?? ''}
                            onChange={e => alterarAcao(i, { prazo: e.target.value })}
                            className={`rounded-xl border px-3 py-1.5 text-xs outline-none ${campo}`}
                          />
                          <button
                            onClick={() => alterarAcao(i, { minha: !a.minha })}
                            className={`rounded-xl border px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider ${campo}`}
                            title="Alterna entre tarefa minha e espera de terceiro"
                          >
                            {a.minha ? 'Minha' : 'Aguarda terceiro'}
                          </button>
                        </div>
                        <p className={`text-[11px] italic leading-relaxed ${suave}`}>“{a.trecho}”</p>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}

          {dados.recusados.length > 0 && (
            <section className="mt-4">
              <h3 className={`mb-1 text-[10px] font-bold uppercase tracking-wider ${suave}`}>
                Recusados na leitura
              </h3>
              {dados.recusados.map((r, i) => (
                <p key={i} className={`text-[11px] ${suave}`}>
                  {r.motivo}
                </p>
              ))}
              <p className={`mt-1 text-[10px] leading-relaxed ${suave}`}>
                Item sem trecho literal da transcrição é recusado, e não corrigido — é o que
                impede a leitura de inventar tarefa que ninguém combinou.
              </p>
            </section>
          )}
        </div>

        <footer className={`flex shrink-0 items-center gap-2 border-t p-4 ${isDark ? 'border-white/10' : 'border-slate-200'}`}>
          <span className={`text-xs ${suave}`}>
            {criadas !== null
              ? `${criadas} ação(ões) criadas.`
              : `${acoesAceitas.size} de ${dados.acoes.length} ações marcadas.`}
          </span>
          <button
            onClick={() => void criar()}
            disabled={criando || acoesAceitas.size === 0 || criadas !== null}
            className={`ml-auto rounded-xl px-4 py-2 text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-40 ${isDark ? 'bg-white text-slate-950 hover:bg-slate-200' : 'bg-slate-900 text-white hover:bg-indigo-600'}`}
          >
            {criando ? 'Criando…' : 'Criar no Hermes'}
          </button>
        </footer>
      </div>
    </div>
  );
};
