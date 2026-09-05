// src/utils/reuniaoAgenda.test.ts
import { describe, it, expect } from 'vitest';
import type { GoogleCalendarEvent } from '../../types';
import type { BancoRespostas } from './bancosRespostas';
import {
  buscarEventoReuniaoAtivoOuProximo,
  casarBancoComEvento,
  resolverBancoAutomatico,
  normalizarTextoAgenda,
  validarInicioGravacao,
  formatarCabecalhoConsentimento,
  extrairFalasJanelaTempo,
  montarPromptUltimosSegundos,
  montarPromptConsultaAcervo,
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

describe('validarInicioGravacao', () => {
  it('permite iniciar quando é gravação individual sem terceiros presentes', () => {
    const res = validarInicioGravacao(false, false);
    expect(res.podeIniciar).toBe(true);
    expect(res.motivo).toBeUndefined();
  });

  it('bloqueia início quando há terceiros presentes e o aviso não foi confirmado', () => {
    const res = validarInicioGravacao(true, false);
    expect(res.podeIniciar).toBe(false);
    expect(res.motivo).toContain('É obrigatório confirmar o aviso e consentimento');
  });

  it('permite iniciar quando há terceiros presentes e o aviso foi devidamente confirmado', () => {
    const res = validarInicioGravacao(true, true);
    expect(res.podeIniciar).toBe(true);
    expect(res.motivo).toBeUndefined();
  });
});

describe('formatarCabecalhoConsentimento', () => {
  it('formata texto de consentimento para reunião com terceiros confirmada', () => {
    const consent = {
      terceirosPresentes: true,
      avisoConfirmado: true,
      confirmadoEm: '2026-09-05T14:30:00.000Z',
    };
    const cabecalho = formatarCabecalhoConsentimento(consent, '05/09/2026 11:30:00');
    expect(cabecalho).toBe(
      'Aviso de Privacidade: Reunião com terceiros. Participantes avisados e consentimento confirmado em 05/09/2026 11:30:00',
    );
  });

  it('formata texto para gravação individual / notas pessoais', () => {
    const consent = {
      terceirosPresentes: false,
      avisoConfirmado: false,
      confirmadoEm: '2026-09-05T14:30:00.000Z',
    };
    const cabecalho = formatarCabecalhoConsentimento(consent);
    expect(cabecalho).toBe(
      'Aviso de Privacidade: Gravação individual / notas pessoais (sem terceiros presentes)',
    );
  });

  it('formata texto padrão para consent nulo', () => {
    const cabecalho = formatarCabecalhoConsentimento(null);
    expect(cabecalho).toBe(
      'Aviso de Privacidade: Gravação individual / notas pessoais (sem terceiros presentes)',
    );
  });
});

describe('extrairFalasJanelaTempo', () => {
  const t0 = new Date('2026-09-05T14:30:00.000Z');
  const t10 = new Date('2026-09-05T14:30:10.000Z');
  const t25 = new Date('2026-09-05T14:30:25.000Z');
  const t45 = new Date('2026-09-05T14:30:45.000Z');
  const t55 = new Date('2026-09-05T14:30:55.000Z');

  const falas = [
    { timestamp: t0, speaker: 'André', text: 'Bom dia a todos.' },
    { timestamp: t10, speaker: 'Interlocutor', text: 'Bom dia, vamos falar do prazo?' },
    { timestamp: t25, speaker: 'André', text: 'Sim, o prazo final é 06/09.' },
    { timestamp: t45, speaker: 'Interlocutor', text: 'E como fica a alocação de recursos?' },
    { timestamp: t55, speaker: 'Interlocutor', text: 'Podemos fechar essa parte agora?' },
  ];

  it('filtra apenas as falas dentro da janela de 30 segundos em relação ao fim', () => {
    const agoraRef = new Date('2026-09-05T14:30:55.000Z');
    // Janela de 30s cobre de 14:30:25 até 14:30:55 (t25, t45, t55)
    const extraidas = extrairFalasJanelaTempo(falas, 30, agoraRef);
    expect(extraidas.length).toBe(3);
    expect(extraidas.map((f) => f.speaker)).toEqual(['André', 'Interlocutor', 'Interlocutor']);
    expect(extraidas[2].text).toBe('Podemos fechar essa parte agora?');
  });

  it('retorna fallback das últimas falas se nenhuma estiver na janela estrita', () => {
    const agoraDistante = new Date('2026-09-05T14:35:00.000Z'); // 4 minutos depois
    const extraidas = extrairFalasJanelaTempo(falas, 30, agoraDistante);
    expect(extraidas.length).toBe(3); // fallback últimas 3 falas
    expect(extraidas[2].text).toBe('Podemos fechar essa parte agora?');
  });

  it('retorna array vazio quando lista de falas é vazia', () => {
    const extraidas = extrairFalasJanelaTempo([], 30);
    expect(extraidas).toEqual([]);
  });
});

describe('montarPromptUltimosSegundos', () => {
  it('gera prompt estruturado com as falas recentes e instruções de concisão', () => {
    const falas = [
      { speaker: 'Interlocutor', text: 'Qual é o valor final da proposta?' },
    ];
    const prompt = montarPromptUltimosSegundos(falas, 'Negociação Contratual');
    expect(prompt).toContain('Negociação Contratual');
    expect(prompt).toContain('Qual é o valor final da proposta?');
    expect(prompt).toContain('máximo de 2 a 3 frases');
  });
});

describe('montarPromptConsultaAcervo', () => {
  it('formata o contexto de reuniões e instrui o assistente a citar título e data', () => {
    const acervo = [
      {
        titulo: 'Alinhamento Q3',
        startedAt: '2026-09-01T10:00:00.000Z',
        transcripts: [
          { speaker: 'João', text: 'Ficou combinado entregar o relatório dia 10.' },
        ],
      },
    ];
    const prompt = montarPromptConsultaAcervo('O que ficou combinado com o João?', acervo);
    expect(prompt).toContain('Alinhamento Q3');
    expect(prompt).toContain('Ficou combinado entregar o relatório dia 10.');
    expect(prompt).toContain('O que ficou combinado com o João?');
    expect(prompt).toContain('Identifique explicitamente o título e a data');
  });
});
