import { describe, expect, it } from 'vitest';
import {
  MAX_CARACTERES_TRECHO,
  MAX_TRECHOS_POR_LOTE,
  SINAL_DE_VIDA_MS,
  SincronizadorTranscricao,
  montarTrechos,
  novoIdTranscricao,
} from './transcricaoAoVivo';

type Dados = Record<string, any>;

/** Servidor de mentira com a mesma regra do functions/transcricao_ao_vivo.py. */
function servidor() {
  const chamadas: Dados[] = [];
  const trechos: Dados[] = [];
  let ultimoSeq = 0;
  let ultimoLote: string | null = null;
  let estado: string | null = null;
  let falhasPendentes = 0;
  let perderResposta = 0;
  const chamar = async (dados: Dados) => {
    chamadas.push(JSON.parse(JSON.stringify(dados)));
    if (falhasPendentes > 0) {
      falhasPendentes -= 1;
      throw new Error('sem rede');
    }
    let resposta: Dados;
    if (dados.acao === 'iniciar') {
      if (estado === null) estado = 'ao_vivo';
      resposta = { status: 'criada', ultimo_seq: ultimoSeq };
    } else if (dados.acao === 'anexar') {
      if (!dados.trechos.length) resposta = { status: 'vivo', ultimo_seq: ultimoSeq };
      else if (dados.lote_id === ultimoLote) resposta = { status: 'ja_gravado', ultimo_seq: ultimoSeq };
      else if (dados.base_seq !== ultimoSeq) resposta = { status: 'conflito', ultimo_seq: ultimoSeq };
      else {
        for (const t of dados.trechos) trechos.push({ seq: ++ultimoSeq, ...t });
        ultimoLote = dados.lote_id;
        resposta = { status: 'gravado', ultimo_seq: ultimoSeq };
      }
    } else if (dados.acao === 'encerrar') {
      estado = 'encerrada';
      resposta = { status: 'encerrada', ultimo_seq: ultimoSeq };
    } else {
      resposta = { status: 'vinculada' };
    }
    if (perderResposta > 0) {
      perderResposta -= 1;
      throw new Error('resposta perdida');
    }
    return resposta;
  };
  return {
    chamar,
    chamadas,
    trechos,
    get estado() { return estado; },
    falhar(n: number) { falhasPendentes = n; },
    perder(n: number) { perderResposta = n; },
  };
}

describe('montarTrechos', () => {
  it('junta falas seguidas do mesmo falante e separa quando o falante muda', () => {
    const { trechos, usados } = montarTrechos([
      { falante: 'Reunião', texto: 'bom dia', tInicio: 1, tFim: 2 },
      { falante: 'Reunião', texto: 'a todos', tInicio: 2, tFim: 3 },
      { falante: 'Você', texto: 'oi', tInicio: 3, tFim: 4 },
    ]);
    expect(usados).toBe(3);
    expect(trechos).toEqual([
      { falante: 'Reunião', texto: 'bom dia a todos', t_inicio: 1, t_fim: 3 },
      { falante: 'Você', texto: 'oi', t_inicio: 3, t_fim: 4 },
    ]);
  });

  it('corta o trecho longo e para no limite de trechos do lote', () => {
    const grande = 'x'.repeat(MAX_CARACTERES_TRECHO - 5);
    const { trechos } = montarTrechos([
      { falante: 'A', texto: grande, tInicio: 0, tFim: 1 },
      { falante: 'A', texto: 'mais texto', tInicio: 1, tFim: 2 },
    ]);
    expect(trechos).toHaveLength(2);

    const muitos = Array.from({ length: MAX_TRECHOS_POR_LOTE + 5 }, (_, i) => ({
      falante: i % 2 ? 'A' : 'B', texto: `fala ${i}`, tInicio: i, tFim: i + 1,
    }));
    const r = montarTrechos(muitos);
    expect(r.trechos).toHaveLength(MAX_TRECHOS_POR_LOTE);
    expect(r.usados).toBe(MAX_TRECHOS_POR_LOTE);
  });
});

describe('novoIdTranscricao', () => {
  it('gera id aceito pelo servidor', () => {
    expect(novoIdTranscricao()).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
  });
});

describe('SincronizadorTranscricao', () => {
  it('inicia, envia lotes em ordem e encerra', async () => {
    const s = servidor();
    const sync = new SincronizadorTranscricao(s.chamar, { titulo: 'Webinário', terceirosPresentes: true });
    await sync.tick();
    expect(s.chamadas[0]).toMatchObject({ acao: 'iniciar', titulo: 'Webinário', terceiros_presentes: true });

    sync.adicionar('Reunião', '  primeira   fala ', 5, 2);
    await sync.tick();
    sync.adicionar('Reunião', 'segunda fala', 15, 1);
    await sync.tick();
    expect(s.trechos.map(t => [t.seq, t.texto])).toEqual([[1, 'primeira fala'], [2, 'segunda fala']]);
    expect(s.trechos[0]).toMatchObject({ t_inicio: 3, t_fim: 5 });

    await sync.encerrar();
    expect(s.estado).toBe('encerrada');
    sync.adicionar('Reunião', 'depois do fim', 20);
    expect(sync.pendentesCount).toBe(0);
  });

  it('reenvia o mesmo lote depois de falha de rede, sem duplicar', async () => {
    const s = servidor();
    const sync = new SincronizadorTranscricao(s.chamar, { titulo: 't', terceirosPresentes: false });
    await sync.tick();
    sync.adicionar('Você', 'fala um', 1);
    s.perder(1); // o servidor gravou, mas a resposta não chegou
    await sync.tick();
    sync.adicionar('Você', 'fala dois', 30); // chega enquanto o primeiro lote está pendente
    await sync.tick();
    await sync.tick();
    const anexos = s.chamadas.filter(c => c.acao === 'anexar' && c.trechos.length);
    expect(anexos[0].lote_id).toBe(anexos[1].lote_id);
    expect(anexos[1].base_seq).toBe(0);
    expect(s.trechos.map(t => t.texto)).toEqual(['fala um', 'fala dois']);
    expect(sync.ultimoSeq).toBe(2);
  });

  it('se o iniciar falhar, tenta de novo e não perde o texto', async () => {
    const s = servidor();
    const sync = new SincronizadorTranscricao(s.chamar, { titulo: 't', terceirosPresentes: false });
    s.falhar(1);
    sync.adicionar('Você', 'guardado', 1);
    await sync.tick();
    expect(s.trechos).toHaveLength(0);
    await sync.tick();
    expect(s.trechos.map(t => t.texto)).toEqual(['guardado']);
  });

  it('manda sinal de vida depois de 30 s sem texto', async () => {
    let agora = 0;
    const s = servidor();
    const sync = new SincronizadorTranscricao(s.chamar, { titulo: 't', terceirosPresentes: false, agora: () => agora });
    await sync.tick();
    agora = SINAL_DE_VIDA_MS - 1;
    await sync.tick();
    expect(s.chamadas.filter(c => c.acao === 'anexar')).toHaveLength(0);
    agora = SINAL_DE_VIDA_MS;
    await sync.tick();
    expect(s.chamadas.filter(c => c.acao === 'anexar')).toEqual([
      { acao: 'anexar', sessao_id: sync.sessaoId, trechos: [] },
    ]);
  });

  it('no conflito reenvia a partir do seq do servidor', async () => {
    const s = servidor();
    const sync = new SincronizadorTranscricao(s.chamar, { titulo: 't', terceirosPresentes: false });
    await sync.tick();
    // outro gravador (não deveria existir) acrescentou um trecho
    await s.chamar({ acao: 'anexar', lote_id: 'outro-lote-1', base_seq: 0, trechos: [{ texto: 'alheio' }] });
    sync.adicionar('Você', 'meu', 1);
    await sync.tick();
    await sync.tick();
    expect(s.trechos.map(t => [t.seq, t.texto])).toEqual([[1, 'alheio'], [2, 'meu']]);
  });

  it('vincular só depois de iniciar', async () => {
    const s = servidor();
    const sync = new SincronizadorTranscricao(s.chamar, { titulo: 't', terceirosPresentes: false });
    await sync.vincular('Título', 'abc');
    expect(s.chamadas).toHaveLength(0);
    await sync.tick();
    await sync.vincular('Título', 'abc12345');
    expect(s.chamadas.at(-1)).toMatchObject({ acao: 'vincular', titulo: 'Título', reuniao_id: 'abc12345' });
  });
});
