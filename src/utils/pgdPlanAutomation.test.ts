import { describe, expect, it } from 'vitest';
import {
  distributePgdPercentages,
  getPgdPeriodFromMonth,
  getPgdTargetPeriod,
  normalizePgdDeliveryIdentity,
} from './pgdPlanAutomation';

describe('getPgdTargetPeriod', () => {
  it('usa o mês atual na primeira quinzena', () => {
    expect(getPgdTargetPeriod(new Date(2026, 6, 15))).toEqual({
      mesAno: '2026-07',
      dataInicio: '2026-07-01',
      dataFim: '2026-07-31',
    });
  });

  it('usa o mês seguinte a partir do dia 16, incluindo virada de ano', () => {
    expect(getPgdTargetPeriod(new Date(2026, 11, 16))).toEqual({
      mesAno: '2027-01',
      dataInicio: '2027-01-01',
      dataFim: '2027-01-31',
    });
  });
});

describe('getPgdPeriodFromMonth', () => {
  it('usa sempre o primeiro e o último dia do mês escolhido', () => {
    expect(getPgdPeriodFromMonth('2028-02')).toEqual({
      mesAno: '2028-02',
      dataInicio: '2028-02-01',
      dataFim: '2028-02-29',
    });
  });
});

describe('normalizePgdDeliveryIdentity', () => {
  it('mantém o histórico quando o status da entrega muda', () => {
    expect(normalizePgdDeliveryIdentity(
      'Contratação de vigilância patrimonial, encaminhada.',
    )).toBe(normalizePgdDeliveryIdentity(
      'Contratação de vigilância patrimonial, concluída.',
    ));
  });
});

describe('distributePgdPercentages', () => {
  it.each([
    [1, [100]],
    [3, [35, 35, 30]],
    [4, [25, 25, 25, 25]],
    [6, [20, 20, 15, 15, 15, 15]],
    [7, [15, 15, 15, 15, 15, 15, 10]],
  ])('distribui %i entregas em blocos de 5', (count, expected) => {
    const values = distributePgdPercentages(count as number);
    expect(values).toEqual(expected);
    expect(values.reduce((sum, value) => sum + value, 0)).toBe(100);
    expect(Math.max(...values) - Math.min(...values)).toBeLessThanOrEqual(5);
  });
});
