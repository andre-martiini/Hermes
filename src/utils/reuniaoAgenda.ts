// src/utils/reuniaoAgenda.ts
// Regras puras para detecção de reunião em curso/próxima e associação
// automática com o banco de respostas correspondente.
//
// Fica separado de React e Firestore para permitir testes unitários rápidos
// e determinísticos sem mocks pesados de banco ou rede.

import type { GoogleCalendarEvent } from '../../types';
import type { BancoRespostas } from './bancosRespostas';

export interface ReuniaoAtivaOuProxima {
  evento: GoogleCalendarEvent;
  emCurso: boolean;
  minutosParaInicio: number; // 0 se em curso
}

export type CriterioCasamentoBanco = 'id' | 'nome_exato' | 'nome_contem' | 'palavras_chave';

export interface CasamentoBancoEvento {
  banco: BancoRespostas;
  evento: GoogleCalendarEvent;
  criterio: CriterioCasamentoBanco;
}

/**
 * Normaliza texto para comparação sem acentos, pontuações e caixa alta/baixa.
 */
export const normalizarTextoAgenda = (texto: string): string =>
  (texto || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

/**
 * Encontra entre os eventos da agenda aquele que está em andamento agora
 * ou que começa nos próximos X minutos (padrão 60 min).
 *
 * Prioridade: reunião em curso > reunião mais próxima a iniciar.
 * Ignora eventos de dia inteiro sem horário fixo (ex: feriados).
 */
export const buscarEventoReuniaoAtivoOuProximo = (
  eventos: readonly GoogleCalendarEvent[],
  agora: Date = new Date(),
  janelaProximaMinutos = 60,
): ReuniaoAtivaOuProxima | null => {
  const agoraMs = agora.getTime();
  const candidatos: Array<{
    evento: GoogleCalendarEvent;
    emCurso: boolean;
    inicioMs: number;
    fimMs: number;
  }> = [];

  for (const ev of eventos) {
    if (!ev.data_inicio) continue;
    // Ignora evento de dia inteiro puro (ex: "2026-09-05" sem "T")
    if (!ev.data_inicio.includes('T')) continue;

    const inicio = new Date(ev.data_inicio);
    const inicioMs = inicio.getTime();
    if (isNaN(inicioMs)) continue;

    const fim = ev.data_fim ? new Date(ev.data_fim) : new Date(inicioMs + 60 * 60 * 1000);
    const fimMs = isNaN(fim.getTime()) ? inicioMs + 60 * 60 * 1000 : fim.getTime();

    // Em curso: agora entre o início (tolerância 5 min antes) e o fim (tolerância 15 min após)
    if (agoraMs >= inicioMs - 5 * 60 * 1000 && agoraMs <= fimMs + 15 * 60 * 1000) {
      candidatos.push({ evento: ev, emCurso: true, inicioMs, fimMs });
    } else if (inicioMs > agoraMs && (inicioMs - agoraMs) <= janelaProximaMinutos * 60 * 1000) {
      candidatos.push({ evento: ev, emCurso: false, inicioMs, fimMs });
    }
  }

  if (candidatos.length === 0) return null;

  // 1. Em curso tem prioridade absoluta
  const emCurso = candidatos.filter((c) => c.emCurso);
  if (emCurso.length > 0) {
    // Se houver mais de um em curso, prefere o que começou mais recentemente
    emCurso.sort((a, b) => b.inicioMs - a.inicioMs);
    return {
      evento: emCurso[0].evento,
      emCurso: true,
      minutosParaInicio: 0,
    };
  }

  // 2. Próximo mais iminente
  const proximos = candidatos.filter((c) => !c.emCurso);
  proximos.sort((a, b) => a.inicioMs - b.inicioMs);
  const maisProximo = proximos[0];
  const minutos = Math.max(0, Math.round((maisProximo.inicioMs - agoraMs) / 60000));
  return {
    evento: maisProximo.evento,
    emCurso: false,
    minutosParaInicio: minutos,
  };
};

/**
 * Casa um evento da agenda com um dos bancos de resposta disponíveis.
 *
 * 1. Critério 1: ID explícito de evento gravado no banco (`eventoCalendarId`).
 * 2. Critério 2: Título normalizado idêntico.
 * 3. Critério 3: Substring contida (nome do banco contido no título ou vice-versa, mín 4 chars).
 * 4. Critério 4: Sobreposição de palavras-chave significativas.
 */
export const casarBancoComEvento = (
  bancos: readonly BancoRespostas[],
  evento: GoogleCalendarEvent,
): CasamentoBancoEvento | null => {
  if (!bancos || bancos.length === 0 || !evento) return null;

  const eventoIds = [evento.google_id, evento.id].filter(Boolean);

  // 1. ID explícito
  for (const b of bancos) {
    if (b.eventoCalendarId && eventoIds.includes(b.eventoCalendarId)) {
      return { banco: b, evento, criterio: 'id' };
    }
  }

  const tituloEvNorm = normalizarTextoAgenda(evento.titulo || '');
  if (!tituloEvNorm) return null;

  // 2. Nome exato
  for (const b of bancos) {
    const nomeNorm = normalizarTextoAgenda(b.nome || '');
    if (nomeNorm && nomeNorm === tituloEvNorm) {
      return { banco: b, evento, criterio: 'nome_exato' };
    }
  }

  // 3. Substring (mínimo de 4 letras para evitar falso positivo)
  for (const b of bancos) {
    const nomeNorm = normalizarTextoAgenda(b.nome || '');
    if (nomeNorm.length >= 4) {
      if (tituloEvNorm.includes(nomeNorm) || nomeNorm.includes(tituloEvNorm)) {
        return { banco: b, evento, criterio: 'nome_contem' };
      }
    }
  }

  // 4. Palavras-chave significativas
  const stopWords = new Set([
    'reuniao', 'reunioes', 'meeting', 'call', 'alinhamento',
    'semanal', 'mensal', 'diaria', 'com', 'para', 'sobre', 'das', 'dos',
  ]);
  const palavrasEv = tituloEvNorm.split(' ').filter((p) => p.length >= 4 && !stopWords.has(p));

  let melhorBanco: BancoRespostas | null = null;
  let maxScore = 0;

  if (palavrasEv.length > 0) {
    for (const b of bancos) {
      const palavrasBanco = normalizarTextoAgenda(b.nome || '')
        .split(' ')
        .filter((p) => p.length >= 4 && !stopWords.has(p));

      let score = 0;
      for (const p of palavrasBanco) {
        if (palavrasEv.includes(p)) score += 1;
      }

      if (score > maxScore) {
        maxScore = score;
        melhorBanco = b;
      }
    }
  }

  if (melhorBanco && maxScore > 0) {
    return { banco: melhorBanco, evento, criterio: 'palavras_chave' };
  }

  return null;
};

/**
 * Orquestra a busca do evento em curso/próximo e a resolução automática do banco.
 */
export const resolverBancoAutomatico = (
  bancos: readonly BancoRespostas[],
  eventos: readonly GoogleCalendarEvent[],
  agora: Date = new Date(),
): {
  bancoSugerido: BancoRespostas | null;
  eventoAtivo: ReuniaoAtivaOuProxima | null;
  criterio?: CriterioCasamentoBanco;
} => {
  const eventoAtivo = buscarEventoReuniaoAtivoOuProximo(eventos, agora);
  if (!eventoAtivo) {
    return { bancoSugerido: null, eventoAtivo: null };
  }

  const casamento = casarBancoComEvento(bancos, eventoAtivo.evento);
  return {
    bancoSugerido: casamento?.banco ?? null,
    eventoAtivo,
    criterio: casamento?.criterio,
  };
};
