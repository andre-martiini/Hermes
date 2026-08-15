import { describe, expect, it } from 'vitest';
import {
    addDays,
    compareGroups,
    computeWeightHeadline,
    daysToReachTarget,
    linearRegression,
    movingAverage,
    weeklyAggregate,
} from './healthAnalytics';

describe('movingAverage', () => {
    it('averages only points within the trailing window', () => {
        const points = [
            { date: '2026-01-01', value: 100 },
            { date: '2026-01-02', value: 98 },
            { date: '2026-01-10', value: 90 }, // fora da janela de 7 dias em relacao ao dia 1
        ];
        const result = movingAverage(points, 7);
        expect(result[0]).toEqual({ date: '2026-01-01', average: 100, count: 1 });
        expect(result[1]).toEqual({ date: '2026-01-02', average: 99, count: 2 });
        expect(result[2]).toEqual({ date: '2026-01-10', average: 90, count: 1 });
    });

    it('returns null average when there are no points', () => {
        expect(movingAverage([], 7)).toEqual([]);
    });
});

describe('weeklyAggregate', () => {
    it('groups points into Monday-start weeks with sum, average and count', () => {
        const points = [
            { date: '2026-06-01', value: 2 }, // segunda
            { date: '2026-06-03', value: 4 }, // quarta, mesma semana
            { date: '2026-06-08', value: 10 }, // segunda seguinte
        ];
        const buckets = weeklyAggregate(points);
        expect(buckets).toHaveLength(2);
        expect(buckets[0]).toMatchObject({ weekStart: '2026-06-01', sum: 6, average: 3, count: 2 });
        expect(buckets[1]).toMatchObject({ weekStart: '2026-06-08', sum: 10, average: 10, count: 1 });
    });
});

describe('linearRegression', () => {
    it('fits a perfect line', () => {
        const points = [
            { x: 0, y: 10 },
            { x: 1, y: 8 },
            { x: 2, y: 6 },
            { x: 3, y: 4 },
        ];
        const result = linearRegression(points);
        expect(result?.slope).toBeCloseTo(-2);
        expect(result?.intercept).toBeCloseTo(10);
    });

    it('returns null with fewer than 2 points', () => {
        expect(linearRegression([{ x: 0, y: 1 }])).toBeNull();
    });
});

describe('daysToReachTarget', () => {
    it('projects forward when the trend moves toward the target', () => {
        // perdendo 0.6kg/semana = -0.0857kg/dia, de 95 para 92 -> ~35 dias
        const days = daysToReachTarget(95, -3 / 7, 92);
        expect(days).toBe(Math.ceil(3 / (3 / 7)));
    });

    it('returns null when the trend is flat or moves away from the target', () => {
        expect(daysToReachTarget(95, 0, 92)).toBeNull();
        expect(daysToReachTarget(95, 0.1, 92)).toBeNull(); // subindo, alvo e abaixo
    });
});

describe('compareGroups', () => {
    it('flags suppressed when either group has fewer than minN samples', () => {
        const withValues = [3, 3, 3, 3, 3];
        const withoutValues = [4, 4];
        const result = compareGroups(withValues, withoutValues, 5);
        expect(result.withN).toBe(5);
        expect(result.withoutN).toBe(2);
        expect(result.suppressed).toBe(true);
        expect(result.withAvg).toBe(3);
        expect(result.withoutAvg).toBe(4);
    });

    it('does not suppress when both groups meet minN', () => {
        const result = compareGroups([1, 2, 3, 4, 5], [5, 5, 5, 5, 5], 5);
        expect(result.suppressed).toBe(false);
    });
});

describe('computeWeightHeadline', () => {
    it('falls back to the raw value when the window has fewer than minPoints records', () => {
        const weights = [
            { date: '2026-08-10', value: 95 },
            { date: '2026-08-14', value: 94.5 },
        ];
        const headline = computeWeightHeadline(weights, 7, 4);
        expect(headline?.isAverage).toBe(false);
        expect(headline?.displayValue).toBe(94.5);
        expect(headline?.windowCount).toBe(2);
        expect(headline?.deltaVsWeekAgo).toBeNull();
    });

    it('uses the 7-day moving average once there are enough points, and compares vs. a week ago', () => {
        const weights = [
            { date: '2026-08-01', value: 96 },
            { date: '2026-08-02', value: 96 },
            { date: '2026-08-03', value: 96 },
            { date: '2026-08-04', value: 96 },
            { date: '2026-08-08', value: 94 },
            { date: '2026-08-09', value: 94 },
            { date: '2026-08-10', value: 94 },
            { date: '2026-08-11', value: 94 },
        ];
        const headline = computeWeightHeadline(weights, 7, 4);
        expect(headline?.isAverage).toBe(true);
        expect(headline?.displayValue).toBe(94);
        expect(headline?.latestRaw).toBe(94);
        expect(headline?.latestRawDate).toBe('2026-08-11');
        expect(headline?.deltaVsWeekAgo).toBeCloseTo(94 - 96);
    });

    it('returns null with no weight records', () => {
        expect(computeWeightHeadline([])).toBeNull();
    });
});

describe('addDays', () => {
    it('adds days across month boundaries', () => {
        expect(addDays('2026-01-30', 3)).toBe('2026-02-02');
    });
});
