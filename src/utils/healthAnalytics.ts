// Funcoes puras de serie temporal usadas pelo modulo Saude (media movel, agregacao
// semanal, regressao linear e comparacao de grupos). Sem dependencia de React/Firestore.

export interface DatedValue {
    date: string; // YYYY-MM-DD
    value: number;
}

export interface MovingAveragePoint {
    date: string;
    average: number | null; // null quando nao ha nenhum ponto na janela
    count: number; // quantos registros entraram na janela
}

export interface WeeklyBucket {
    weekStart: string; // segunda-feira da semana, YYYY-MM-DD
    values: number[];
    sum: number;
    average: number;
    count: number;
}

export interface LinearRegressionResult {
    slope: number; // variacao de y por unidade de x
    intercept: number;
}

export interface GroupComparison {
    withAvg: number | null;
    withoutAvg: number | null;
    withN: number;
    withoutN: number;
    suppressed: boolean; // true quando algum dos grupos tem n abaixo do minimo
}

const DAY_MS = 24 * 60 * 60 * 1000;

export const parseLocalDate = (dateStr: string): Date => {
    const [y, m, d] = dateStr.split('-').map(Number);
    return new Date(y, (m || 1) - 1, d || 1);
};

export const formatLocalISO = (date: Date): string => {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
};

export const addDays = (dateStr: string, days: number): string => {
    const date = parseLocalDate(dateStr);
    date.setDate(date.getDate() + days);
    return formatLocalISO(date);
};

export const daysSinceEpoch = (dateStr: string): number => Math.round(parseLocalDate(dateStr).getTime() / DAY_MS);

/**
 * Media movel de N dias corridos (nao N pontos): para cada ponto, olha para tras
 * `windowDays - 1` dias em relacao a data do calendario, nao em relacao ao indice do
 * array. Isso importa porque o peso, por exemplo, nao e registrado todo dia.
 */
export function movingAverage(points: DatedValue[], windowDays: number): MovingAveragePoint[] {
    const sorted = [...points].sort((a, b) => a.date.localeCompare(b.date));
    const times = sorted.map(p => parseLocalDate(p.date).getTime());
    return sorted.map((point, index) => {
        const pointTime = times[index];
        const windowStart = pointTime - (windowDays - 1) * DAY_MS;
        const windowValues: number[] = [];
        for (let i = 0; i <= index; i++) {
            if (times[i] >= windowStart && times[i] <= pointTime) windowValues.push(sorted[i].value);
        }
        const count = windowValues.length;
        const average = count > 0 ? windowValues.reduce((s, v) => s + v, 0) / count : null;
        return { date: point.date, average, count };
    });
}

/** Agrupa por semana (segunda a domingo). Retorna soma, media e contagem por semana. */
export function weeklyAggregate(points: DatedValue[]): WeeklyBucket[] {
    const buckets = new Map<string, number[]>();
    for (const p of points) {
        const date = parseLocalDate(p.date);
        const day = date.getDay(); // 0=domingo .. 6=sabado
        const diffToMonday = day === 0 ? -6 : 1 - day;
        date.setDate(date.getDate() + diffToMonday);
        const weekStart = formatLocalISO(date);
        if (!buckets.has(weekStart)) buckets.set(weekStart, []);
        buckets.get(weekStart)!.push(p.value);
    }
    return [...buckets.entries()]
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([weekStart, values]) => ({
            weekStart,
            values,
            sum: values.reduce((s, v) => s + v, 0),
            average: values.reduce((s, v) => s + v, 0) / values.length,
            count: values.length,
        }));
}

/** Regressao linear simples (minimos quadrados). Retorna null com menos de 2 pontos ou x constante. */
export function linearRegression(points: { x: number; y: number }[]): LinearRegressionResult | null {
    const n = points.length;
    if (n < 2) return null;
    const meanX = points.reduce((s, p) => s + p.x, 0) / n;
    const meanY = points.reduce((s, p) => s + p.y, 0) / n;
    let num = 0;
    let den = 0;
    for (const p of points) {
        num += (p.x - meanX) * (p.y - meanY);
        den += (p.x - meanX) ** 2;
    }
    if (den === 0) return null;
    const slope = num / den;
    const intercept = meanY - slope * meanX;
    return { slope, intercept };
}

/**
 * Numero de dias ate `currentValue + slopePerDay * dias === targetValue`, seguindo a
 * tendencia real. Retorna null se a tendencia for plana ou se afastar do alvo.
 */
export function daysToReachTarget(currentValue: number, slopePerDay: number, targetValue: number): number | null {
    if (!Number.isFinite(slopePerDay) || slopePerDay === 0) return null;
    const days = (targetValue - currentValue) / slopePerDay;
    if (!Number.isFinite(days) || days <= 0) return null;
    return Math.ceil(days);
}

export interface WeightHeadline {
    displayValue: number; // media movel, ou o registro bruto quando a janela nao tem dados suficientes
    isAverage: boolean;
    windowCount: number; // quantos registros entraram na janela dos ultimos `windowDays`
    latestRaw: number;
    latestRawDate: string;
    deltaVsWeekAgo: number | null; // media atual vs. media de `windowDays` dias atras
}

/**
 * Numero principal do card de peso: media movel de `windowDays` dias, com fallback para o
 * registro bruto quando a janela tiver menos de `minPoints` registros. A variacao compara a
 * media atual com a media de `windowDays` dias atras (nao com o registro anterior).
 */
export function computeWeightHeadline(weights: DatedValue[], windowDays: number = 7, minPoints: number = 4): WeightHeadline | null {
    if (weights.length === 0) return null;
    const sorted = [...weights].sort((a, b) => a.date.localeCompare(b.date));
    const series = movingAverage(sorted, windowDays);
    const latest = series[series.length - 1];
    const latestRaw = sorted[sorted.length - 1];
    const isAverage = latest.count >= minPoints;
    const displayValue = isAverage ? (latest.average as number) : latestRaw.value;

    const weekAgoDate = addDays(latest.date, -windowDays);
    let comparisonPoint: MovingAveragePoint | undefined;
    for (let i = series.length - 1; i >= 0; i--) {
        if (series[i].date <= weekAgoDate) {
            comparisonPoint = series[i];
            break;
        }
    }
    const deltaVsWeekAgo = isAverage && comparisonPoint && comparisonPoint.count >= minPoints
        ? (latest.average as number) - (comparisonPoint.average as number)
        : null;

    return {
        displayValue,
        isAverage,
        windowCount: latest.count,
        latestRaw: latestRaw.value,
        latestRawDate: latestRaw.date,
        deltaVsWeekAgo,
    };
}

/** Compara a media de dois grupos (ex.: dias com treino de forca vs. sem) e sinaliza n baixo. */
export function compareGroups(withValues: number[], withoutValues: number[], minN: number = 5): GroupComparison {
    const withN = withValues.length;
    const withoutN = withoutValues.length;
    return {
        withAvg: withN > 0 ? withValues.reduce((s, v) => s + v, 0) / withN : null,
        withoutAvg: withoutN > 0 ? withoutValues.reduce((s, v) => s + v, 0) / withoutN : null,
        withN,
        withoutN,
        suppressed: withN < minN || withoutN < minN,
    };
}
