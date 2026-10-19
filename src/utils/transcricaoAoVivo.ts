/**
 * Envia a transcrição da reunião ao Gaspar aos poucos, para o Claude ler ao vivo.
 *
 * O motor de gravação (useMeetingRecordingEngine) entrega cada resultado final
 * do Deepgram em `adicionar`; a cada `tick` (~10 s) os fragmentos pendentes
 * viram um lote, agrupando falas seguidas do mesmo falante, e vão à callable
 * `transcricaoAoVivo` (functions/transcricao_ao_vivo.py). Um lote por vez: se
 * a chamada falhar, o MESMO lote (mesmo `lote_id` e `base_seq`) é reenviado no
 * tick seguinte, e o servidor não o duplica. Sem texto novo por 30 s, manda só
 * um sinal de vida, para o Claude saber que a sessão segue no ar.
 */

export type ChamarTranscricao = (dados: Record<string, unknown>) => Promise<{ status?: string; ultimo_seq?: number }>;

interface Fragmento {
  falante: string;
  texto: string;
  tInicio: number;
  tFim: number;
}

interface Trecho {
  falante: string;
  texto: string;
  t_inicio: number;
  t_fim: number;
}

interface Lote {
  loteId: string;
  base: number;
  trechos: Trecho[];
}

export const MAX_TRECHOS_POR_LOTE = 100;
export const MAX_CARACTERES_LOTE = 50000;
export const MAX_CARACTERES_TRECHO = 1500;
export const SINAL_DE_VIDA_MS = 30000;

export function novoIdTranscricao(): string {
  const bruto = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
  return bruto.replace(/[^A-Za-z0-9]/g, '').slice(0, 32);
}

/**
 * Junta fragmentos seguidos do mesmo falante em trechos de até
 * MAX_CARACTERES_TRECHO e para no limite do lote. Devolve os trechos e
 * quantos fragmentos usou (o resto fica para o próximo lote).
 */
export function montarTrechos(fragmentos: Fragmento[]): { trechos: Trecho[]; usados: number } {
  const trechos: Trecho[] = [];
  let total = 0;
  let usados = 0;
  for (const f of fragmentos) {
    if (total + f.texto.length > MAX_CARACTERES_LOTE && usados > 0) break;
    const ultimo = trechos[trechos.length - 1];
    if (ultimo && ultimo.falante === f.falante && ultimo.texto.length + 1 + f.texto.length <= MAX_CARACTERES_TRECHO) {
      ultimo.texto = `${ultimo.texto} ${f.texto}`;
      ultimo.t_fim = Math.max(ultimo.t_fim, f.tFim);
    } else {
      if (trechos.length >= MAX_TRECHOS_POR_LOTE) break;
      trechos.push({ falante: f.falante, texto: f.texto.slice(0, 4000), t_inicio: f.tInicio, t_fim: f.tFim });
    }
    total += f.texto.length;
    usados += 1;
  }
  return { trechos, usados };
}

export class SincronizadorTranscricao {
  readonly sessaoId: string;
  private iniciada = false;
  private encerrada = false;
  private baseSeq = 0;
  private pendentes: Fragmento[] = [];
  private emVoo: Lote | null = null;
  private ultimoEnvioMs: number;
  private cadeia: Promise<void> = Promise.resolve();

  constructor(
    private readonly chamar: ChamarTranscricao,
    private readonly opcoes: { titulo: string; terceirosPresentes: boolean; sessaoId?: string; agora?: () => number },
  ) {
    this.sessaoId = opcoes.sessaoId ?? novoIdTranscricao();
    this.ultimoEnvioMs = this.agora();
  }

  private agora(): number {
    return this.opcoes.agora ? this.opcoes.agora() : Date.now();
  }

  /** Um resultado final do Deepgram. `tFim` e `duracao` em segundos desde o início da gravação. */
  adicionar(falante: string, texto: string, tFim: number, duracao = 0): void {
    const limpo = texto.replace(/\s+/g, ' ').trim();
    if (!limpo || this.encerrada) return;
    const fim = Math.max(0, tFim);
    this.pendentes.push({ falante, texto: limpo, tInicio: Math.max(0, fim - Math.max(0, duracao || 0)), tFim: fim });
  }

  /** Chamado a cada ~10 s. Nunca rejeita: falha fica para o próximo tick. */
  tick(): Promise<void> {
    this.cadeia = this.cadeia.then(() => this.passo()).catch(err => {
      console.warn('Transcrição ao vivo: envio adiado para o próximo ciclo.', err);
    });
    return this.cadeia;
  }

  get pendentesCount(): number {
    return this.pendentes.length + (this.emVoo ? this.emVoo.trechos.length : 0);
  }

  get ultimoSeq(): number {
    return this.baseSeq;
  }

  private async passo(): Promise<void> {
    if (!this.iniciada) {
      const r = await this.chamar({
        acao: 'iniciar',
        sessao_id: this.sessaoId,
        titulo: this.opcoes.titulo,
        terceiros_presentes: this.opcoes.terceirosPresentes,
      });
      this.iniciada = true;
      this.baseSeq = Number(r?.ultimo_seq ?? 0);
    }
    if (!this.emVoo && this.pendentes.length) {
      const { trechos, usados } = montarTrechos(this.pendentes);
      this.pendentes.splice(0, usados);
      this.emVoo = { loteId: novoIdTranscricao(), base: this.baseSeq, trechos };
    }
    if (this.emVoo) {
      const lote = this.emVoo;
      const r = await this.chamar({
        acao: 'anexar',
        sessao_id: this.sessaoId,
        lote_id: lote.loteId,
        base_seq: lote.base,
        trechos: lote.trechos,
      });
      if (r?.status === 'conflito') {
        // O servidor está noutro seq (não deveria acontecer com um só gravador): reenvia dali.
        this.baseSeq = Number(r.ultimo_seq ?? this.baseSeq);
        lote.base = this.baseSeq;
        return;
      }
      this.baseSeq = Number(r?.ultimo_seq ?? this.baseSeq);
      this.emVoo = null;
      this.ultimoEnvioMs = this.agora();
      return;
    }
    if (this.agora() - this.ultimoEnvioMs >= SINAL_DE_VIDA_MS) {
      await this.chamar({ acao: 'anexar', sessao_id: this.sessaoId, trechos: [] });
      this.ultimoEnvioMs = this.agora();
    }
  }

  /** Esvazia o que falta (até 3 tentativas) e marca a sessão como encerrada. */
  async encerrar(): Promise<void> {
    this.encerrada = true;
    for (let i = 0; i < 3 && (this.pendentes.length || this.emVoo); i += 1) {
      await this.tick();
    }
    if (!this.iniciada) return;
    this.cadeia = this.cadeia
      .then(async () => { await this.chamar({ acao: 'encerrar', sessao_id: this.sessaoId }); })
      .catch(err => { console.warn('Transcrição ao vivo: não consegui marcar a sessão como encerrada.', err); });
    await this.cadeia;
  }

  /** Depois de salvar a reunião: título definitivo e id do documento em `reunioes`. */
  async vincular(titulo: string, reuniaoId: string | null): Promise<void> {
    if (!this.iniciada) return;
    this.cadeia = this.cadeia
      .then(async () => { await this.chamar({ acao: 'vincular', sessao_id: this.sessaoId, titulo, reuniao_id: reuniaoId }); })
      .catch(err => { console.warn('Transcrição ao vivo: não consegui vincular a reunião salva.', err); });
    await this.cadeia;
  }
}
