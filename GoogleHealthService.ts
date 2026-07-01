import { HealthWeight, ExerciseLog } from './types';

const CLIENT_ID = "1003307358410-o3tbms16qbisurm47vb667plt3c27n1g.apps.googleusercontent.com";
const TOKEN_STORAGE_KEY = 'hermes_google_health_token';
const GOOGLE_FIT_ESTIMATED_STEPS_SOURCE = 'derived:com.google.step_count.delta:com.google.android.gms:estimated_steps';
// Sessões que não representam caminhada/exercício: 0=em veículo, 3=parado, 72=sono.
const NON_EXERCISE_ACTIVITY_TYPES = new Set([0, 3, 72]);
const GOOGLE_HEALTH_SLEEP_SCOPE = "https://www.googleapis.com/auth/googlehealth.sleep.readonly";

// Google Fit: steps, distance, calories, active minutes, weight and sleep fallback.
// Health Connect sleep is intentionally not requested by default: accounts without API access
// receive 403 even after consent, which adds friction to every sync.
const SCOPES = [
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.body.read",
    "https://www.googleapis.com/auth/fitness.location.read",
    "https://www.googleapis.com/auth/fitness.sleep.read",
].join(" ");
const REQUIRED_FIT_SCOPES = new Set([
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.body.read",
    "https://www.googleapis.com/auth/fitness.location.read",
    "https://www.googleapis.com/auth/fitness.sleep.read",
]);

type SavedGoogleHealthToken = {
    token?: string;
    expiry?: number;
    scope?: string;
};

type SessionWalkTotals = {
    sessions: number;
    steps: number;
    distanceM: number;
    durationMin: number;
};

export class GoogleHealthService {
    private static accessToken: string | null = null;
    private static tokenExpiry: number = 0;
    private static grantedScopes: Set<string> = new Set();
    private static pendingAuth: Promise<string> | null = null;

    private static parseScopes(scope?: string) {
        return new Set((scope || '').split(/\s+/).filter(Boolean));
    }

    private static hasRequiredFitScopes(scope?: string) {
        if (!scope) return false;
        const grantedScopes = this.parseScopes(scope);
        return [...REQUIRED_FIT_SCOPES].every(requiredScope => grantedScopes.has(requiredScope));
    }

    private static hasScope(scope: string) {
        return this.grantedScopes.has(scope);
    }

    private static clearSavedToken() {
        this.accessToken = null;
        this.tokenExpiry = 0;
        this.grantedScopes = new Set();
        localStorage.removeItem(TOKEN_STORAGE_KEY);
    }

    private static loadSavedToken() {
        const rawSaved = localStorage.getItem(TOKEN_STORAGE_KEY);
        if (!rawSaved) return false;

        try {
            const { token, expiry, scope } = JSON.parse(rawSaved) as SavedGoogleHealthToken;
            if (typeof token === 'string' && typeof expiry === 'number' && Date.now() < expiry && this.hasRequiredFitScopes(scope)) {
                this.accessToken = token;
                this.tokenExpiry = expiry;
                this.grantedScopes = this.parseScopes(scope);
                return true;
            }
        } catch (error) {
            console.warn('[GoogleHealth] Ignoring invalid saved token:', error);
        }

        this.clearSavedToken();
        return false;
    }

    private static saveToken(token: string, scope: string) {
        this.accessToken = token;
        this.tokenExpiry = Date.now() + (55 * 60 * 1000);
        this.grantedScopes = this.parseScopes(scope);
        localStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify({
            token,
            expiry: this.tokenExpiry,
            scope,
        }));
    }

    static async authorize() {
        if (this.loadSavedToken()) {
            return this.accessToken!;
        }

        if (this.pendingAuth) return this.pendingAuth;

        this.pendingAuth = new Promise<string>((resolve, reject) => {
            if (!(window as any).google) {
                reject(new Error("Google Identity Services not loaded."));
                return;
            }

            const client = (window as any).google.accounts.oauth2.initTokenClient({
                client_id: CLIENT_ID,
                scope: SCOPES,
                callback: (response: any) => {
                    if (response.error) {
                        reject(new Error(typeof response.error === 'string' ? response.error : 'Google authorization failed.'));
                    } else if (!response.access_token || !this.hasRequiredFitScopes(response.scope)) {
                        this.clearSavedToken();
                        reject(new Error(`Google did not grant all required Google Fit scopes. Granted: ${response.scope || 'none'}`));
                    } else {
                        this.saveToken(response.access_token, response.scope);
                        resolve(response.access_token);
                    }
                },
            });

            client.requestAccessToken({ prompt: '' });
        });

        try {
            return await this.pendingAuth;
        } finally {
            this.pendingAuth = null;
        }
    }

    private static formatCivilTime(date: Date) {
        const pad = (n: number) => n.toString().padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    }

    private static async fetchHealthV4(dataType: string, startTime: Date, endTime: Date) {
        if (!this.accessToken) await this.authorize();
        if (!this.hasScope(GOOGLE_HEALTH_SLEEP_SCOPE)) {
            console.warn(`[HealthConnect] Skipping ${dataType}: optional Google Health scope was not granted.`);
            return null;
        }

        const filter = `${dataType}.interval.civil_start_time >= "${this.formatCivilTime(startTime)}" AND ${dataType}.interval.civil_start_time <= "${this.formatCivilTime(endTime)}"`;
        const url = `https://health.googleapis.com/v4/users/me/dataTypes/${dataType}/dataPoints?filter=${encodeURIComponent(filter)}`;

        console.log(`[HealthConnect] Fetching ${dataType}...`);
        const response = await fetch(url, {
            headers: { Authorization: `Bearer ${this.accessToken}`, Accept: 'application/json' }
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            console.error(`[HealthConnect] Error fetching ${dataType}:`, response.status, err);
            return null;
        }

        const data = await response.json();
        console.log(`[HealthConnect] Received ${dataType}:`, data);
        return data;
    }

    private static async settle<T>(label: string, promise: Promise<T>): Promise<T | null> {
        try {
            return await promise;
        } catch (error) {
            console.warn(`[GoogleHealth] ${label} skipped:`, error);
            return null;
        }
    }

    private static async fetchFitAggregate(dataTypeNames: string[], startMs: number, endMs: number) {
        return this.fetchFitAggregateBy(
            dataTypeNames.map(dataTypeName => ({ dataTypeName })),
            startMs,
            endMs
        );
    }

    private static async fetchFitAggregateBy(
        aggregateBy: Array<{ dataTypeName: string } | { dataSourceId: string }>,
        startMs: number,
        endMs: number
    ) {
        if (!this.accessToken) await this.authorize();

        const body = {
            aggregateBy,
            bucketByTime: { durationMillis: endMs - startMs },
            startTimeMillis: startMs,
            endTimeMillis: endMs,
        };

        console.log('[GoogleFit] Fetching:', aggregateBy);
        const response = await fetch('https://fitness.googleapis.com/fitness/v1/users/me/dataset:aggregate', {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${this.accessToken}`,
                'Content-Type': 'application/json',
                Accept: 'application/json',
            },
            body: JSON.stringify(body),
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            console.error('[GoogleFit] Error:', response.status, err);
            return null;
        }

        const data = await response.json();
        console.log('[GoogleFit] Received:', data);
        return data;
    }

    private static async fetchFitDataSources(dataTypeName: string) {
        if (!this.accessToken) await this.authorize();

        const params = new URLSearchParams({ dataTypeName });
        const response = await fetch(`https://fitness.googleapis.com/fitness/v1/users/me/dataSources?${params.toString()}`, {
            headers: {
                Authorization: `Bearer ${this.accessToken}`,
                Accept: 'application/json',
            },
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            console.error('[GoogleFit] Data sources error:', response.status, err);
            return [];
        }

        const data = await response.json();
        return data?.dataSource ?? [];
    }

    private static async fetchFitDataset(dataSourceId: string, startMs: number, endMs: number) {
        if (!this.accessToken) await this.authorize();

        const startNs = BigInt(Math.trunc(startMs)) * BigInt(1_000_000);
        const endNs = BigInt(Math.trunc(endMs)) * BigInt(1_000_000);
        const datasetId = `${startNs}-${endNs}`;
        const url = `https://fitness.googleapis.com/fitness/v1/users/me/dataSources/${encodeURIComponent(dataSourceId)}/datasets/${datasetId}`;
        const response = await fetch(url, {
            headers: {
                Authorization: `Bearer ${this.accessToken}`,
                Accept: 'application/json',
            },
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            console.error('[GoogleFit] Dataset error:', response.status, err);
            return null;
        }

        return response.json();
    }

    private static getDataSourceLabel(source: any) {
        const app = source.application?.name || source.application?.packageName;
        const device = [source.device?.manufacturer, source.device?.model].filter(Boolean).join(' ');
        return source.dataStreamName || device || app || source.dataStreamId || 'Unknown source';
    }

    private static async fetchFitActivitySessions(startTime: Date, endTime: Date) {
        if (!this.accessToken) await this.authorize();

        const params = new URLSearchParams({
            startTime: startTime.toISOString(),
            endTime: endTime.toISOString(),
        });

        console.log('[GoogleFit] Fetching activity sessions...');
        const response = await fetch(`https://fitness.googleapis.com/fitness/v1/users/me/sessions?${params.toString()}`, {
            headers: {
                Authorization: `Bearer ${this.accessToken}`,
                Accept: 'application/json',
            },
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            console.error('[GoogleFit] Activity sessions error:', response.status, err);
            return [];
        }

        const data = await response.json();
        return (data?.session ?? []).filter((session: any) =>
            !NON_EXERCISE_ACTIVITY_TYPES.has(Number(session.activityType))
        );
    }

    // Passos/distância são absorvidos apenas de sessões de caminhada/exercício
    // registradas no Google Health/Fit — o agregado diário de passos mistura
    // fontes pouco confiáveis (contagem passiva do celular) e não é usado.
    private static async fetchSessionWalkTotals(startTime: Date, endTime: Date): Promise<SessionWalkTotals> {
        const sessions = await this.fetchFitActivitySessions(startTime, endTime);
        const totals: SessionWalkTotals = { sessions: sessions.length, steps: 0, distanceM: 0, durationMin: 0 };

        for (const session of sessions.slice(0, 20)) {
            const startMs = Math.max(Number(session.startTimeMillis), startTime.getTime());
            const endMs = Math.min(Number(session.endTimeMillis), endTime.getTime());
            if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) continue;

            const data = await this.fetchFitAggregateBy(
                [
                    { dataSourceId: GOOGLE_FIT_ESTIMATED_STEPS_SOURCE },
                    { dataTypeName: 'com.google.distance.delta' },
                ],
                startMs,
                endMs
            );
            totals.steps += this.getAggregateValue(data, 'step_count', 'intVal');
            totals.distanceM += this.getAggregateValue(data, 'distance', 'fpVal');
            totals.durationMin += Math.round((endMs - startMs) / 60000);
        }

        console.log('[GoogleFit] Session walk totals:', totals);
        return totals;
    }

    private static getAggregateValue(data: any, dataTypeName: string, valueType: 'intVal' | 'fpVal') {
        const dataset = (data?.bucket?.[0]?.dataset ?? []).find((ds: any) =>
            String(ds.dataSourceId ?? '').includes(dataTypeName)
        );
        const points: any[] = dataset?.point ?? [];
        return points.reduce((acc, point) => acc + (point.value?.[0]?.[valueType] ?? 0), 0);
    }

    private static async fetchFitSleepSessions(startTime: Date, endTime: Date) {
        if (!this.accessToken) await this.authorize();

        const params = new URLSearchParams({
            startTime: startTime.toISOString(),
            endTime: endTime.toISOString(),
            activityType: '72',
        });

        console.log('[GoogleFit] Fetching sleep sessions...');
        const response = await fetch(`https://fitness.googleapis.com/fitness/v1/users/me/sessions?${params.toString()}`, {
            headers: {
                Authorization: `Bearer ${this.accessToken}`,
                Accept: 'application/json',
            },
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            console.error('[GoogleFit] Sleep sessions error:', response.status, err);
            return null;
        }

        const data = await response.json();
        console.log('[GoogleFit] Received sleep sessions:', data);
        return data;
    }

    private static parseFitSleep(data: any): ExerciseLog['sleep'] | undefined {
        const allPoints: any[] = (data?.bucket ?? [])
            .flatMap((bucket: any) => bucket.dataset ?? [])
            .flatMap((dataset: any) => dataset.point ?? []);

        let totalMinutes = 0;
        let deepMinutes = 0;
        let remMinutes = 0;

        for (const point of allPoints) {
            const sleepStage = point.value?.[0]?.intVal;
            if (![0, 2, 4, 5, 6].includes(sleepStage)) continue;

            const startNanos = BigInt(point.startTimeNanos ?? 0);
            const endNanos = BigInt(point.endTimeNanos ?? 0);
            if (endNanos <= startNanos) continue;

            const minutes = Number((endNanos - startNanos) / BigInt(60_000_000_000));
            totalMinutes += minutes;
            if (sleepStage === 5) deepMinutes += minutes;
            if (sleepStage === 6) remMinutes += minutes;
        }

        if (totalMinutes <= 0) return undefined;
        return {
            totalMinutes,
            ...(deepMinutes > 0 ? { deepMinutes } : {}),
            ...(remMinutes > 0 ? { remMinutes } : {}),
        };
    }

    private static parseFitSleepSessions(data: any): ExerciseLog['sleep'] | undefined {
        const sleepSessions: any[] = data?.session ?? [];
        const totalSleepMs = sleepSessions.reduce((acc, session) => {
            const startMs = Number(session.startTimeMillis);
            const endMs = Number(session.endTimeMillis);
            return Number.isFinite(startMs) && Number.isFinite(endMs) && endMs > startMs
                ? acc + (endMs - startMs)
                : acc;
        }, 0);

        return totalSleepMs > 0 ? { totalMinutes: Math.round(totalSleepMs / 60000) } : undefined;
    }

    static async getDailyTelemetry(date: Date): Promise<Partial<ExerciseLog>> {
        const start = new Date(date);
        start.setHours(0, 0, 0, 0);
        const end = new Date(date);
        end.setHours(23, 59, 59, 999);

        const [fitData, sessionWalk, healthSleepData, fitSleepData, fitSleepSessionData] = await Promise.all([
            this.settle('activity aggregate', this.fetchFitAggregate(
                ['com.google.calories.expended'],
                start.getTime(),
                end.getTime()
            )),
            this.settle('session walk totals', this.fetchSessionWalkTotals(start, end)),
            this.settle('Health Connect sleep', this.fetchHealthV4('sleep', start, end)),
            this.settle('Fit sleep aggregate', this.fetchFitAggregate(
                ['com.google.sleep.segment'],
                start.getTime(),
                end.getTime()
            )),
            this.settle('Fit sleep sessions', this.fetchFitSleepSessions(start, end)),
        ]);

        const summary: Partial<ExerciseLog> = {};

        const steps = sessionWalk?.steps ?? 0;
        const distanceM = sessionWalk?.distanceM ?? 0;
        const walkMinutes = sessionWalk?.durationMin ?? 0;
        const calories = this.getAggregateValue(fitData, 'calories', 'fpVal');

        if (steps > 0 || distanceM > 0 || walkMinutes > 0) {
            summary.walk = {
                done: walkMinutes,
                steps,
                distance: distanceM / 1000,
            };
        }
        if (calories > 0) summary.calories = Math.round(calories);

        console.log('[GoogleFit] Daily telemetry parsed:', {
            date: date.toLocaleDateString(),
            sessions: sessionWalk?.sessions ?? 0,
            steps,
            distanceKm: Number((distanceM / 1000).toFixed(2)),
            walkMinutes,
            totalCaloriesIncludingBmr: Math.round(calories),
        });

        if (healthSleepData?.dataPoints && healthSleepData.dataPoints.length > 0) {
            let totalSleepSec = 0;
            for (const point of healthSleepData.dataPoints) {
                const interval = point.sleep?.interval ?? point.exercise?.interval ?? point.interval;
                const startTime = interval?.startTime ?? point.startTime ?? point.start_time;
                const endTime = interval?.endTime ?? point.endTime ?? point.end_time;
                const s = startTime ? new Date(startTime).getTime() : NaN;
                const e = endTime ? new Date(endTime).getTime() : NaN;
                if (!isNaN(s) && !isNaN(e)) totalSleepSec += (e - s) / 1000;
            }
            if (totalSleepSec > 0) {
                summary.sleep = { totalMinutes: Math.round(totalSleepSec / 60) };
            }
        }
        summary.sleep ??= this.parseFitSleep(fitSleepData);
        summary.sleep ??= this.parseFitSleepSessions(fitSleepSessionData);

        return summary;
    }

    static async getWeight(date: Date): Promise<Partial<HealthWeight> | null> {
        const end = new Date(date);
        end.setHours(23, 59, 59, 999);
        const start = new Date(end);
        start.setDate(start.getDate() - 30);
        start.setHours(0, 0, 0, 0);

        const [aggregateData, weightSources] = await Promise.all([
            this.settle('weight aggregate', this.fetchFitAggregate(
                ['com.google.weight'],
                start.getTime(),
                end.getTime()
            )),
            this.settle('weight sources', this.fetchFitDataSources('com.google.weight')),
        ]);

        const sourceDatasets = await Promise.all((weightSources ?? []).slice(0, 10).map(async (source: any) => ({
            source,
            data: await this.settle(`weight dataset ${this.getDataSourceLabel(source)}`, this.fetchFitDataset(source.dataStreamId, start.getTime(), end.getTime())),
        })));

        const rawPoints = sourceDatasets
            .flatMap(({ source, data }) => (data?.point ?? []).map((point: any) => ({
                point,
                sourceLabel: this.getDataSourceLabel(source),
            })))
            .filter(({ point }) => typeof point.value?.[0]?.fpVal === 'number');

        if (rawPoints.length > 0) {
            const latest = rawPoints.reduce((best, current) =>
                BigInt(current.point.endTimeNanos ?? 0) > BigInt(best.point.endTimeNanos ?? 0) ? current : best
            );
            console.log('[GoogleFit] Latest weight parsed:', {
                weight: latest.point.value?.[0]?.fpVal,
                source: latest.sourceLabel,
            });
            return { weight: latest.point.value?.[0]?.fpVal };
        }

        const aggregatePoints: any[] = (aggregateData?.bucket ?? [])
            .flatMap((b: any) => (b.dataset ?? []).flatMap((ds: any) => ds.point ?? []));

        if (aggregatePoints.length > 0) {
            const latest = aggregatePoints.reduce((a, b) =>
                BigInt(b.endTimeNanos ?? 0) > BigInt(a.endTimeNanos ?? 0) ? b : a
            );
            const aggregateWeight = latest.value?.[0]?.fpVal;
            if (typeof aggregateWeight === 'number') {
                console.log('[GoogleFit] Aggregate weight parsed:', aggregateWeight);
                return { weight: aggregateWeight };
            }
        }
        return null;
    }
}
