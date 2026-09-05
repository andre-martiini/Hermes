// src/utils/reuniaoAgenda.test.ts
import { describe, it, expect } from 'vitest';
import type { GoogleCalendarEvent } from '../../types';
import type { BancoRespostas } from './bancosRespostas';
import {
  buscarEventoReuniaoAtivoOuProximo,
  casarBancoComEvento,
  resolverBancoAutomatico,
  normalizarTextoAgenda,
} from './reuniaoAgenda';

const criarBancoMock = (
  id: string,
  nome: string,
  eventoCalendarId?: string,
): BancoRespostas => ({
  id,
  nome,
  cartoes: [],
  criadoEm: '2026-09-01T10:00:00.000Z',
  atualizadoEm: '2026-09-01T10:00:00.000Z',
  eventoCalendarId,
});

const criarEventoMock = (
  id: string,
  titulo: string,
  dataInicio: string,
  dataFim: string,
  googleId?: string,
): GoogleCalendarEvent => ({
  id,
  google_id: googleId || id,
  titulo,
  data_inicio: dataInicio,
  data_fim: dataFim,
  last_sync: '2026-09-05T10:00:00.000Z',
});

describe('normalizarTextoAgenda', () => {
  it('remove acentos, pontuação e converte para minúsculas', () => {
    expect(normalizarTextoAgenda('Reunião de Diretoria: Alinhamento Estratégico!'))
      .toBe('reuniao de diretoria alinhamento estrategico');
  });
});

describe('buscarEventoReuniaoAtivoOuProximo', () => {
  const agora = new Date('2026-09-05T14:15:00.000Z');

  it('detecta reunião em curso no momento atual', () => {
    const eventos = [
      criarEventoMock(
        'ev1',
        'Reunião em Curso',
        '2026-09-05T14:00:00.000Z',
        '2026-09-05T15:00:00.000Z',
      ),
    ];
    const resultado = buscarEventoReuniaoAtivoOuProximo(eventos, agora);
    expect(resultado).not.toBeNull();
    expect(resultado?.evento.id).toBe('ev1');
    expect(resultado?.emCurso).toBe(true);
    expect(resultado?.minutosParaInicio).toBe(0);
  });

  it('detecta reunião próxima dentro da janela de 60 minutos', () => {
    const eventos = [
      criarEventoMock(
        'ev2',
        'Reunião Futura',
        '2026-09-05T14:45:00.000Z',
        '2026-09-05T15:45:00.000Z',
      ),
    ];
    const resultado = buscarEventoReuniaoAtivoOuProximo(eventos, agora);
    expect(resultado).not.toBeNull();
    expect(resultado?.evento.id).toBe('ev2');
    expect(resultado?.emCurso).toBe(false);
    expect(resultado?.minutosParaInicio).toBe(30);
  });

  it('ignora reunião distante (mais de 60 minutos)', () => {
    const eventos = [
      criarEventoMock(
        'ev3',
        'Reunião Tarde',
        '2026-09-05T18:00:00.000Z',
        '2026-09-05T19:00:00.000Z',
      ),
    ];
    const resultado = buscarEventoReuniaoAtivoOuProximo(eventos, agora);
    expect(resultado).toBeNull();
  });

  it('ignora eventos de dia inteiro sem horário fixo', () => {
    const eventos = [
      criarEventoMock(
        'ev4',
        'Feriado Municipal',
        '2026-09-05',
        '2026-09-05',
      ),
    ];
    const resultado = buscarEventoReuniaoAtivoOuProximo(eventos, agora);
    expect(resultado).toBeNull();
  });

  it('prioriza reunião em curso sobre reunião próxima', () => {
    const eventos = [
      criarEventoMock(
        'ev_proxima',
        'Reunião Próxima',
        '2026-09-05T14:45:00.000Z',
        '2026-09-05T15:45:00.000Z',
      ),
      criarEventoMock(
        'ev_em_curso',
        'Reunião Acontecendo',
        '2026-09-05T14:00:00.000Z',
        '2026-09-05T15:00:00.000Z',
      ),
    ];
    const resultado = buscarEventoReuniaoAtivoOuProximo(eventos, agora);
    expect(resultado?.evento.id).toBe('ev_em_curso');
    expect(resultado?.emCurso).toBe(true);
  });
});

describe('casarBancoComEvento', () => {
  it('casa com prioridade máxima pelo eventoCalendarId explícito', () => {
    const bancos = [
      criarBancoMock('banco1', 'Diretoria OKF', 'cal_123'),
      criarBancoMock('banco2', 'Reunião Qualquer'),
    ];
    const evento = criarEventoMock('ev_x', 'Assuntos Diversos', '2026-09-05T14:00:00Z', '2026-09-05T15:00:00Z', 'cal_123');
    const casado = casarBancoComEvento(bancos, evento);

    expect(casado).not.toBeNull();
    expect(casado?.banco.id).toBe('banco1');
    expect(casado?.criterio).toBe('id');
  });

  it('casa por nome exato normalizado', () => {
    const bancos = [
      criarBancoMock('banco_mago', 'Mago das Finanças'),
    ];
    const evento = criarEventoMock('ev1', 'MAGO DAS FINANÇAS', '2026-09-05T14:00:00Z', '2026-09-05T15:00:00Z');
    const casado = casarBancoComEvento(bancos, evento);

    expect(casado).not.toBeNull();
    expect(casado?.banco.id).toBe('banco_mago');
    expect(casado?.criterio).toBe('nome_exato');
  });

  it('casa por substring contida (ex: nome do banco contido no título da reunião)', () => {
    const bancos = [
      criarBancoMock('banco_clc', 'Comissão Licitação'),
    ];
    const evento = criarEventoMock('ev1', 'Reunião da Comissão Licitação Semanal', '2026-09-05T14:00:00Z', '2026-09-05T15:00:00Z');
    const casado = casarBancoComEvento(bancos, evento);

    expect(casado).not.toBeNull();
    expect(casado?.banco.id).toBe('banco_clc');
    expect(casado?.criterio).toBe('nome_contem');
  });

  it('casa por sobreposição de palavras-chave significativas', () => {
    const bancos = [
      criarBancoMock('banco_pesquisa', 'Grupo Pesquisa Inteligência Artificial'),
    ];
    const evento = criarEventoMock('ev1', 'Alinhamento Semanal Pesquisa Inteligência', '2026-09-05T14:00:00Z', '2026-09-05T15:00:00Z');
    const casado = casarBancoComEvento(bancos, evento);

    expect(casado).not.toBeNull();
    expect(casado?.banco.id).toBe('banco_pesquisa');
    expect(casado?.criterio).toBe('palavras_chave');
  });

  it('retorna null se não houver correspondência plausível', () => {
    const bancos = [
      criarBancoMock('banco_medico', 'Consulta Médica'),
    ];
    const evento = criarEventoMock('ev1', 'Aula de Tênis', '2026-09-05T14:00:00Z', '2026-09-05T15:00:00Z');
    const casado = casarBancoComEvento(bancos, evento);

    expect(casado).toBeNull();
  });
});

describe('resolverBancoAutomatico', () => {
  const agora = new Date('2026-09-05T14:05:00.000Z');

  it('resolve o banco sugerido e o evento em curso', () => {
    const bancos = [
      criarBancoMock('b_orcamento', 'Orçamento 2027'),
    ];
    const eventos = [
      criarEventoMock('ev_orc', 'Discussão Orçamento 2027', '2026-09-05T14:00:00.000Z', '2026-09-05T15:00:00.000Z'),
    ];
    const resolucao = resolverBancoAutomatico(bancos, eventos, agora);

    expect(resolucao.eventoAtivo).not.toBeNull();
    expect(resolucao.eventoAtivo?.evento.id).toBe('ev_orc');
    expect(resolucao.bancoSugerido).not.toBeNull();
    expect(resolucao.bancoSugerido?.id).toBe('b_orcamento');
  });

  it('retorna evento ativo mas sem banco quando não há banco correspondente', () => {
    const bancos = [
      criarBancoMock('b_outros', 'Outro Assunto'),
    ];
    const eventos = [
      criarEventoMock('ev_orc', 'Reunião Inédita', '2026-09-05T14:00:00.000Z', '2026-09-05T15:00:00.000Z'),
    ];
    const resolucao = resolverBancoAutomatico(bancos, eventos, agora);

    expect(resolucao.eventoAtivo).not.toBeNull();
    expect(resolucao.bancoSugerido).toBeNull();
  });
});
