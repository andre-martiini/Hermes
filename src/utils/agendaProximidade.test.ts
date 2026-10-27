/**
 * Proximidade e conflito da agenda, com o relógio injetado.
 *
 * O que protege: os limites. "Exatamente 30 minutos" e "exatamente 15" são
 * onde um `<` no lugar de `<=` passaria despercebido — o compromisso das 9h
 * mudaria de cor um minuto tarde.
 */
import { describe, expect, it } from 'vitest';

import {
    LIMITE_ATENCAO_MIN, LIMITE_URGENTE_MIN, calcularDestaque, descreverTempo, detectarConflitos,
    eventosDoDia, hhmmParaMin, minutosDoRelogio, rotuloHora, textoDoConflito,
} from './agendaProximidade';

const min = (hhmm: string) => hhmmParaMin(hhmm) as number;

const AGENDA = [
    { titulo: 'Sessão de pilates', inicio: '09:00', fim: '09:50' },
    { titulo: 'Buscar Alexandre na escola', inicio: '09:35', fim: '09:55' },
    { titulo: 'Acupuntura', inicio: '13:30', fim: '14:30' },
    { titulo: 'Cirurgia da Avó', inicio: null, fim: null, dia_inteiro: true },
];

describe('limites nomeados', () => {
    it('são 30 e 15 minutos', () => {
        expect(LIMITE_ATENCAO_MIN).toBe(30);
        expect(LIMITE_URGENTE_MIN).toBe(15);
    });
});

describe('calcularDestaque — nível pelo tempo que falta', () => {
    const eventos = eventosDoDia(AGENDA, []);
    const nivelEm = (hhmm: string) => calcularDestaque(eventos, min(hhmm));

    it('31 min antes: normal', () => {
        expect(nivelEm('08:29')).toMatchObject({ nivel: 'normal', minutos: 31 });
    });
    it('30 min antes: já é atenção (limite inclusivo)', () => {
        expect(nivelEm('08:30')).toMatchObject({ nivel: 'atencao', minutos: 30 });
    });
    it('29 min antes: atenção', () => {
        expect(nivelEm('08:31')).toMatchObject({ nivel: 'atencao', minutos: 29 });
    });
    it('16 min antes: ainda atenção', () => {
        expect(nivelEm('08:44')).toMatchObject({ nivel: 'atencao', minutos: 16 });
    });
    it('15 min antes: já é urgente (limite inclusivo)', () => {
        expect(nivelEm('08:45')).toMatchObject({ nivel: 'urgente', minutos: 15 });
    });
    it('14 min antes: urgente', () => {
        expect(nivelEm('08:46')).toMatchObject({ nivel: 'urgente', minutos: 14 });
    });
    it('1 min antes: urgente, e o alvo é o próximo', () => {
        const d = nivelEm('08:59');
        expect(d.nivel).toBe('urgente');
        expect(d.alvo?.titulo).toBe('Sessão de pilates');
    });

    it('dentro do compromisso: agora, com os minutos que faltam para terminar', () => {
        const d = nivelEm('13:40');
        expect(d.nivel).toBe('agora');
        expect(d.alvo?.titulo).toBe('Acupuntura');
        expect(d.minutos).toBe(50);
    });
    it('no minuto exato do início já está dentro (agora)', () => {
        expect(nivelEm('13:30').nivel).toBe('agora');
    });
    it('no minuto exato do fim já não está mais', () => {
        const d = calcularDestaque(eventosDoDia([{ titulo: 'X', inicio: '10:00', fim: '11:00' }], []), min('11:00'));
        expect(d.alvo).toBeNull();
    });

    it('quem vai começar manda sobre quem está em andamento (o aviso chega a tempo)', () => {
        // Pilates 9:00–9:50 em andamento; o das 9:35 começa em 25 min -> atenção.
        const d = nivelEm('09:10');
        expect(d.nivel).toBe('atencao');
        expect(d.alvo?.titulo).toBe('Buscar Alexandre na escola');
        expect(d.minutos).toBe(25);
    });

    it('sem mais compromissos: normal e sem alvo', () => {
        expect(nivelEm('20:00')).toEqual({ alvo: null, nivel: 'normal', minutos: null });
    });

    it('dia inteiro não é compromisso com horário', () => {
        expect(eventosDoDia(AGENDA, []).map(e => e.titulo)).not.toContain('Cirurgia da Avó');
    });
});

describe('relógio do dispositivo', () => {
    it('lê hora e minuto locais', () => {
        expect(minutosDoRelogio(new Date(2026, 9, 27, 8, 31, 59))).toBe(8 * 60 + 31);
    });
});

describe('eventosDoDia', () => {
    it('sem hora de fim ocupa 1h, como no resumo matinal', () => {
        const [e] = eventosDoDia([{ titulo: 'X', inicio: '13:50', fim: null }], []);
        expect(e.fim - e.inicio).toBe(60);
        expect(e.fimDeclarado).toBe(false);
    });
    it('fim antes do início é ignorado (usa a duração padrão)', () => {
        const [e] = eventosDoDia([{ titulo: 'X', inicio: '13:50', fim: '13:00' }], []);
        expect(e.fim).toBe(min('14:50'));
    });
    it('hora inválida sai', () => {
        expect(eventosDoDia([{ titulo: 'X', inicio: '25:00', fim: null }], [])).toEqual([]);
    });
    it('fora da agenda entra marcado, e não duplica o que já está na agenda', () => {
        const eventos = eventosDoDia(
            [{ titulo: 'Acupuntura', inicio: '13:30', fim: '14:30' }],
            [
                { titulo: 'Conselho de Escola — EMEF', inicio: '13:50', fim: null },
                { titulo: 'acupuntura', inicio: '13:30', fim: null },
            ],
        );
        expect(eventos.map(e => [e.titulo, e.foraDaAgenda])).toEqual([
            ['Acupuntura', false],
            ['Conselho de Escola — EMEF', true],
        ]);
    });
});

describe('detectarConflitos', () => {
    it('sobreposição aponta os dois compromissos', () => {
        const c = detectarConflitos(eventosDoDia(AGENDA, []));
        expect(c.pares).toHaveLength(1);
        expect(c.pares[0].a.titulo).toBe('Sessão de pilates');
        expect(c.pares[0].b.titulo).toBe('Buscar Alexandre na escola');
        expect(c.ids.size).toBe(2);
    });

    it('um que termina quando o outro começa não conflita', () => {
        const c = detectarConflitos(eventosDoDia([
            { titulo: 'A', inicio: '10:00', fim: '11:00' },
            { titulo: 'B', inicio: '11:00', fim: '12:00' },
        ], []));
        expect(c.pares).toEqual([]);
    });

    it('compromisso fora da agenda participa do cálculo', () => {
        const c = detectarConflitos(eventosDoDia(
            [{ titulo: 'Acupuntura', inicio: '13:30', fim: '14:30' }],
            [{ titulo: 'Conselho de Escola', inicio: '13:50', fim: null }],
        ));
        expect(c.pares).toHaveLength(1);
        expect(textoDoConflito(c.pares[0])).toBe(
            'Conselho de Escola 13h50 bate com Acupuntura 13h30. Um deles não está na agenda.');
    });

    it('sem sobreposição, sem conflito', () => {
        expect(detectarConflitos(eventosDoDia([
            { titulo: 'A', inicio: '08:00', fim: '09:00' }, { titulo: 'B', inicio: '10:00', fim: '11:00' },
        ], [])).pares).toEqual([]);
    });

    it('muda quando um horário muda (não é gravado)', () => {
        const antes = detectarConflitos(eventosDoDia(AGENDA, []));
        const movida = AGENDA.map(e => e.titulo === 'Buscar Alexandre na escola' ? { ...e, inicio: '10:00', fim: '10:20' } : e);
        expect(antes.pares).toHaveLength(1);
        expect(detectarConflitos(eventosDoDia(movida, [])).pares).toHaveLength(0);
    });
});

describe('rótulos', () => {
    it('hora e tempo', () => {
        expect(rotuloHora(min('09:00'))).toBe('9h');
        expect(rotuloHora(min('13:50'))).toBe('13h50');
        expect(descreverTempo(25)).toBe('em 25 min');
        expect(descreverTempo(90)).toBe('em 1h30');
        expect(descreverTempo(120)).toBe('em 2h');
        expect(descreverTempo(1)).toBe('agora');
    });
});
