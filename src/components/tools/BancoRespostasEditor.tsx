// src/components/tools/BancoRespostasEditor.tsx
// Editor dos bancos de resposta usados na assistência ao vivo.
//
// Esta tela é também a futura tela de REVISÃO: quando o Hermes passar a gerar
// cartões a partir dos documentos, é aqui que eles vão aparecer para serem
// aceitos antes de valerem numa reunião. Por isso o editor é por cartão, e não
// um campo de texto livre — a revisão precisa ser item a item.

import React, { useEffect, useMemo, useState } from 'react';
import {
  atualizarBanco,
  criarBanco,
  listarBancos,
  removerBanco,
} from '../../services/bancosRespostasService';
import {
  cartaoVazio,
  conferirBanco,
  exportarCartoesParaJson,
  gatilhosDeTexto,
  importarCartoesDeJson,
  linhasDeTexto,
  MODELO_PARA_IA,
  type BancoRespostas,
} from '../../utils/bancosRespostas';
import type { CartaoResposta } from '../../utils/cartoesReuniao';
import { BANCO_MAGO } from '../../utils/bancoRespostasMago';

interface Props {
  isDark: boolean;
  onClose: () => void;
  onBancosMudaram?: () => void;
}

export const BancoRespostasEditor: React.FC<Props> = ({ isDark, onClose, onBancosMudaram }) => {
  const [bancos, setBancos] = useState<BancoRespostas[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const [idEmEdicao, setIdEmEdicao] = useState<string | null>(null);
  const [nome, setNome] = useState('');
  const [descricao, setDescricao] = useState('');
  const [eventoCalendarId, setEventoCalendarId] = useState('');
  const [cartoes, setCartoes] = useState<CartaoResposta[]>([]);
  const [cartaoAberto, setCartaoAberto] = useState<string | null>(null);
  const [importAberto, setImportAberto] = useState(false);
  const [jsonColado, setJsonColado] = useState('');
  const [aviso, setAviso] = useState<string | null>(null);

  const painel = isDark ? 'bg-slate-900 border-white/10' : 'bg-white border-slate-200';
  const campo = isDark
    ? 'bg-slate-950 border-white/10 text-slate-100 placeholder:text-slate-600'
    : 'bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-400';
  const titulo = isDark ? 'text-slate-100' : 'text-slate-900';
  const suave = isDark ? 'text-slate-400' : 'text-slate-500';

  const recarregar = async () => {
    setCarregando(true);
    try {
      setBancos(await listarBancos());
      setErro(null);
    } catch (e) {
      console.error('Erro ao listar bancos de resposta', e);
      setErro('Não foi possível carregar os bancos. O que você já digitou continua aqui.');
    } finally {
      setCarregando(false);
    }
  };

  useEffect(() => {
    void recarregar();
  }, []);

  const problemas = useMemo(() => conferirBanco(cartoes), [cartoes]);
  const problemasDoCartao = (id: string) => problemas.filter((p) => p.cartaoId === id);

  const abrirBanco = (banco: BancoRespostas) => {
    setIdEmEdicao(banco.id);
    setNome(banco.nome);
    setDescricao(banco.descricao ?? '');
    setEventoCalendarId(banco.eventoCalendarId ?? '');
    setCartoes(banco.cartoes);
    setCartaoAberto(banco.cartoes[0]?.id ?? null);
  };

  const novoBanco = (base: CartaoResposta[] = [cartaoVazio()], nomeInicial = '') => {
    setIdEmEdicao(null);
    setNome(nomeInicial);
    setDescricao('');
    setEventoCalendarId('');
    setCartoes(base);
    setCartaoAberto(base[0]?.id ?? null);
  };

  const alterarCartao = (id: string, mudanca: Partial<CartaoResposta>) =>
    setCartoes((atuais) => atuais.map((c) => (c.id === id ? { ...c, ...mudanca } : c)));

  const salvar = async () => {
    setSalvando(true);
    try {
      if (idEmEdicao) await atualizarBanco(idEmEdicao, nome, cartoes, descricao, eventoCalendarId);
      else {
        const novoId = await criarBanco(nome, cartoes, descricao, eventoCalendarId);
        setIdEmEdicao(novoId);
      }
      await recarregar();
      onBancosMudaram?.();
      setErro(null);
    } catch (e) {
      console.error('Erro ao salvar banco de resposta', e);
      setErro('Não deu para salvar. Nada foi perdido — tente de novo.');
    } finally {
      setSalvando(false);
    }
  };

  const excluir = async (banco: BancoRespostas) => {
    if (!window.confirm(`Excluir o banco "${banco.nome}"? Não dá para desfazer.`)) return;
    try {
      await removerBanco(banco.id);
      if (idEmEdicao === banco.id) novoBanco();
      await recarregar();
      onBancosMudaram?.();
    } catch (e) {
      console.error('Erro ao remover banco de resposta', e);
      setErro('Não deu para excluir.');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm">
      <div className={`flex h-full max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border shadow-2xl ${painel}`}>
        <header className={`flex shrink-0 items-center gap-3 border-b p-4 ${isDark ? 'border-white/10' : 'border-slate-200'}`}>
          <div className="min-w-0 flex-1">
            <h2 className={`text-base font-bold ${titulo}`}>Bancos de resposta</h2>
            <p className={`truncate text-xs ${suave}`}>
              Os cartões que sobem sozinhos durante a reunião, quando a pergunta aparece na fala do outro lado.
            </p>
          </div>
          <button onClick={onClose} className={`rounded-xl border px-3 py-2 text-xs font-bold uppercase tracking-wider ${campo}`}>
            Fechar
          </button>
        </header>

        {erro && (
          <p className={`shrink-0 px-4 py-2 text-xs font-semibold ${isDark ? 'bg-rose-500/10 text-rose-300' : 'bg-rose-50 text-rose-700'}`}>
            {erro}
          </p>
        )}

        <div className="flex min-h-0 flex-1">
          <aside className={`flex w-64 shrink-0 flex-col gap-2 overflow-y-auto border-r p-3 ${isDark ? 'border-white/10' : 'border-slate-200'}`}>
            <button
              onClick={() => novoBanco()}
              className={`rounded-xl border px-3 py-2 text-xs font-bold ${campo}`}
            >
              + Novo banco
            </button>
            <button
              onClick={() => novoBanco([...BANCO_MAGO], 'MAGO — SETEC e FDI')}
              className={`rounded-xl border px-3 py-2 text-[11px] font-semibold ${campo}`}
              title="Carrega os 14 cartões do MAGO como ponto de partida. Só vira banco depois de salvar."
            >
              Começar do exemplo (MAGO)
            </button>

            {carregando ? (
              <p className={`px-1 py-2 text-xs ${suave}`}>Carregando…</p>
            ) : bancos.length === 0 ? (
              <p className={`px-1 py-2 text-xs leading-relaxed ${suave}`}>
                Nenhum banco ainda. Crie um do zero ou comece do exemplo.
              </p>
            ) : (
              bancos.map((banco) => (
                <div key={banco.id} className={`rounded-xl border p-2 ${idEmEdicao === banco.id ? (isDark ? 'border-indigo-400/50 bg-indigo-500/10' : 'border-indigo-300 bg-indigo-50') : campo}`}>
                  <button onClick={() => abrirBanco(banco)} className="w-full text-left">
                    <p className={`truncate text-xs font-bold ${titulo}`}>{banco.nome}</p>
                    <p className={`text-[10px] ${suave}`}>
                      {banco.cartoes.length} cartões{banco.eventoCalendarId ? ' • 📅 Vinculado' : ''}
                    </p>
                  </button>
                  <button
                    onClick={() => void excluir(banco)}
                    className={`mt-1 text-[10px] font-bold uppercase tracking-wider ${suave} hover:text-rose-500`}
                  >
                    Excluir
                  </button>
                </div>
              ))
            )}
          </aside>

          <section className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                placeholder="Nome do banco — ex.: Reunião com a SETEC, 01/09"
                className={`flex-1 rounded-xl border px-3 py-2 text-sm font-semibold outline-none ${campo}`}
              />
              <input
                value={descricao}
                onChange={(e) => setDescricao(e.target.value)}
                placeholder="Descrição (opcional)"
                className={`flex-1 rounded-xl border px-3 py-2 text-sm outline-none ${campo}`}
              />
            </div>
            <div className="mt-2 flex items-center gap-2">
              <span className={`text-[11px] font-semibold whitespace-nowrap ${suave}`}>ID Reunião Calendar:</span>
              <input
                value={eventoCalendarId}
                onChange={(e) => setEventoCalendarId(e.target.value)}
                placeholder="Vínculo com evento do Google Calendar (opcional, ex: google_id ou ID do evento)"
                className={`flex-1 rounded-xl border px-3 py-1.5 text-xs outline-none ${campo}`}
              />
            </div>

            {problemas.length > 0 && (
              <p className={`mt-3 rounded-xl px-3 py-2 text-[11px] font-semibold leading-relaxed ${isDark ? 'bg-amber-500/10 text-amber-300' : 'bg-amber-50 text-amber-800'}`}>
                {problemas.length} ponto(s) a resolver antes de usar este banco numa reunião. Cada cartão mostra o seu.
              </p>
            )}

            <div className="mt-3 flex flex-wrap gap-2">
              <button
                onClick={() => setImportAberto(a => !a)}
                className={`rounded-xl border px-3 py-1.5 text-[11px] font-bold ${campo}`}
              >
                {importAberto ? 'Fechar importação' : 'Importar JSON'}
              </button>
              <button
                onClick={() => {
                  void navigator.clipboard.writeText(MODELO_PARA_IA);
                  setAviso('Modelo copiado. Cole numa IA junto com os seus documentos e traga o JSON de volta.');
                }}
                className={`rounded-xl border px-3 py-1.5 text-[11px] font-bold ${campo}`}
                title="Instruções prontas para pedir os cartões a uma IA externa"
              >
                Copiar modelo para IA
              </button>
              <button
                onClick={() => {
                  void navigator.clipboard.writeText(exportarCartoesParaJson(cartoes));
                  setAviso(`${cartoes.length} cartão(ões) copiados como JSON.`);
                }}
                disabled={cartoes.length === 0}
                className={`rounded-xl border px-3 py-1.5 text-[11px] font-bold disabled:opacity-40 ${campo}`}
              >
                Exportar JSON
              </button>
            </div>

            {aviso && (
              <p className={`mt-2 rounded-xl px-3 py-2 text-[11px] font-semibold ${isDark ? 'bg-emerald-500/10 text-emerald-300' : 'bg-emerald-50 text-emerald-800'}`}>
                {aviso}
              </p>
            )}

            {importAberto && (
              <div className={`mt-2 rounded-2xl border p-3 ${campo}`}>
                <textarea
                  value={jsonColado}
                  onChange={e => setJsonColado(e.target.value)}
                  placeholder='Cole aqui o JSON dos cartões. Aceita uma lista, ou um objeto com a chave "cartoes".'
                  rows={6}
                  className={`w-full rounded-xl border px-3 py-2 font-mono text-[11px] outline-none ${campo}`}
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    onClick={() => {
                      const { cartoes: lidos, recusados } = importarCartoesDeJson(jsonColado);
                      if (lidos.length > 0) {
                        setCartoes(atuais => [...atuais, ...lidos]);
                        setCartaoAberto(null);
                      }
                      const partes = [
                        lidos.length > 0 ? `${lidos.length} cartão(ões) importados.` : 'Nenhum cartão importado.',
                        ...recusados.map(r => `Item ${r.posicao} recusado: ${r.motivo}`),
                      ];
                      setAviso(partes.join(' '));
                      if (lidos.length > 0) { setJsonColado(''); setImportAberto(false); }
                    }}
                    className={`rounded-xl px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider ${isDark ? 'bg-white text-slate-950' : 'bg-slate-900 text-white'}`}
                  >
                    Importar
                  </button>
                  <button
                    onClick={() => { setJsonColado(''); setImportAberto(false); }}
                    className={`rounded-xl border px-3 py-1.5 text-[11px] font-bold ${campo}`}
                  >
                    Cancelar
                  </button>
                </div>
                <p className={`mt-2 text-[10px] leading-relaxed ${suave}`}>
                  Os cartões entram no banco que está aberto, somando-se aos que já existem. Nada é
                  salvo antes de você clicar em salvar — e cartão recusado é sempre dito, com o motivo.
                </p>
              </div>
            )}

            <div className="mt-3 space-y-2">
              {cartoes.map((cartao, indice) => {
                const meus = problemasDoCartao(cartao.id);
                const aberto = cartaoAberto === cartao.id;
                return (
                  <article key={cartao.id} className={`rounded-2xl border ${campo}`}>
                    <button
                      onClick={() => setCartaoAberto(aberto ? null : cartao.id)}
                      className="flex w-full items-center gap-2 p-3 text-left"
                    >
                      <span className={`text-[10px] font-bold ${suave}`}>{indice + 1}</span>
                      <span className={`min-w-0 flex-1 truncate text-sm font-semibold ${titulo}`}>
                        {cartao.pergunta || 'Cartão sem pergunta'}
                      </span>
                      {meus.length > 0 && (
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${isDark ? 'bg-amber-500/20 text-amber-300' : 'bg-amber-100 text-amber-800'}`}>
                          {meus.length}
                        </span>
                      )}
                      <span className={`text-xs ${suave}`}>{aberto ? '−' : '+'}</span>
                    </button>

                    {aberto && (
                      <div className="space-y-2 px-3 pb-3">
                        <input
                          value={cartao.pergunta}
                          onChange={(e) => alterarCartao(cartao.id, { pergunta: e.target.value })}
                          placeholder="A pergunta, como ela é feita em voz alta"
                          className={`w-full rounded-xl border px-3 py-2 text-sm outline-none ${campo}`}
                        />
                        <textarea
                          value={cartao.gatilhos.join('\n')}
                          onChange={(e) => alterarCartao(cartao.id, { gatilhos: gatilhosDeTexto(e.target.value) })}
                          placeholder="Gatilhos — uma frase por linha, ou separadas por vírgula. São elas que fazem o cartão subir."
                          rows={3}
                          className={`w-full rounded-xl border px-3 py-2 text-xs outline-none ${campo}`}
                        />
                        <textarea
                          value={cartao.resposta.join('\n')}
                          onChange={(e) => alterarCartao(cartao.id, { resposta: linhasDeTexto(e.target.value) })}
                          placeholder="Resposta — uma frase curta por linha. Ninguém lê parágrafo falando."
                          rows={4}
                          className={`w-full rounded-xl border px-3 py-2 text-sm outline-none ${campo}`}
                        />
                        <textarea
                          value={(cartao.numeros ?? []).join('\n')}
                          onChange={(e) => alterarCartao(cartao.id, { numeros: linhasDeTexto(e.target.value) })}
                          placeholder="Números que não podem sair errados — um por linha (opcional)"
                          rows={2}
                          className={`w-full rounded-xl border px-3 py-2 text-xs outline-none ${campo}`}
                        />
                        <textarea
                          value={cartao.naoDizer ?? ''}
                          onChange={(e) => alterarCartao(cartao.id, { naoDizer: e.target.value })}
                          placeholder="O que NÃO dizer (opcional) — é o campo que evita o estrago"
                          rows={2}
                          className={`w-full rounded-xl border px-3 py-2 text-xs outline-none ${campo}`}
                        />

                        {meus.map((p, i) => (
                          <p key={i} className={`text-[11px] font-semibold ${isDark ? 'text-amber-300' : 'text-amber-800'}`}>
                            {p.mensagem}
                          </p>
                        ))}

                        <button
                          onClick={() => setCartoes((atuais) => atuais.filter((c) => c.id !== cartao.id))}
                          className={`text-[10px] font-bold uppercase tracking-wider ${suave} hover:text-rose-500`}
                        >
                          Remover cartão
                        </button>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              <button
                onClick={() => {
                  const novo = cartaoVazio();
                  setCartoes((atuais) => [...atuais, novo]);
                  setCartaoAberto(novo.id);
                }}
                className={`rounded-xl border px-3 py-2 text-xs font-bold ${campo}`}
              >
                + Cartão
              </button>
              <button
                onClick={() => void salvar()}
                disabled={salvando || cartoes.length === 0}
                className={`rounded-xl px-4 py-2 text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-40 ${isDark ? 'bg-white text-slate-950 hover:bg-slate-200' : 'bg-slate-900 text-white hover:bg-indigo-600'}`}
              >
                {salvando ? 'Salvando…' : idEmEdicao ? 'Salvar alterações' : 'Criar banco'}
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};
