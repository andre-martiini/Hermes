import { HealthWeight, ExerciseLog } from './types';

const CLIENT_ID = "1003307358410-o3tbms16qbisurm47vb667plt3c27n1g.apps.googleusercontent.com";
const TOKEN_STORAGE_KEY = 'hermes_google_health_token';

// Health Connect: sleep. Google Fit: steps, distance, calories, active minutes, weight, sleep fallback.
const SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.body.read",
    "https://www.googleapis.com/auth/fitness.location.read",
    "https://www.googleapis.com/auth/fitness.sleep.read",
].join(" ");
const REQUIRED_SCOPES = new Set(SCOPES.split(/\s+/));

type SavedGoogleHealthToken = {
    token?: string;
    expiry?: number;
    scope?: string;
};

export class GoogleHealthService {
    private static accessToken: string | null = null;
    private static tokenExpiry: number = 0;
    private static pendingAuth: Promise<string> | null = null;

    private static hasRequiredScopes(scope?: string) {
        if (!scope) return false;
        const grantedScopes = new Set(scope.split(/\s+/).filter(Boolean));
        return [...REQUIRED_SCOPES].every(requiredScope => grantedScopes.has(requiredScope));
    }

    private static clearSavedToken() {
        this.accessToken = null;
        this.tokenExpiry = 0;
        localStorage.removeItem(TOKEN_STORAGE_KEY);
    }

    private static loadSavedToken() {
        const rawSaved = localStorage.getItem(TOKEN_STORAGE_KEY);
        if (!rawSaved) return false;

        try {
            const { token, expiry, scope } = JSON.parse(rawSaved) as SavedGoogleHealthToken;
            if (typeof token === 'string' && typeof expiry === 'number' && Date.now() < expiry && this.hasRequiredScopes(scope)) {
                this.accessToken = token;
                this.tokenExpiry = expiry;
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
                    } else if (!response.access_token || !this.hasRequiredScopes(response.scope)) {
                        this.clearSavedToken();
                        reject(new Error(`Google did not grant all required health scopes. Granted: ${response.scope || 'none'}`));
                    } else {
                        this.saveToken(response.access_token, response.scope);
                        resolve(response.access_token);
                    }
                },
            });

            client.requestAccessToken({ prompt: 'consent' });
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

    private static async fetchFitAggregate(dataTypeNames: string[], startMs: number, endMs: number) {
        if (!this.accessToken) await this.authorize();

        const body = {
            aggregateBy: dataTypeNames.map(dataTypeName => ({ dataTypeName })),
            bucketByTime: { durationMillis: endMs - startMs },
            startTimeMillis: startMs,
            endTimeMillis: endMs,
        };

        console.log('[GoogleFit] Fetching:', dataTypeNames);
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

        const [fitData, healthSleepData, fitSleepData, fitSleepSessionData] = await Promise.all([
            this.fetchFitAggregate(
                ['com.google.step_count.delta', 'com.google.distance.delta', 'com.google.calories.expended', 'com.google.active_minutes'],
                start.getTime(),
                end.getTime()
            ),
            this.fetchHealthV4('sleep', start, end),
            this.fetchFitAggregate(
                ['com.google.sleep.segment'],
                start.getTime(),
                end.getTime()
            ),
            this.fetchFitSleepSessions(start, end),
        ]);

        const summary: Partial<ExerciseLog> = {};

        const datasets: any[] = fitData?.bucket?.[0]?.dataset ?? [];
        let steps = 0, distanceM = 0, calories = 0, activeMin = 0;

        for (const ds of datasets) {
            const points: any[] = ds.point ?? [];
            const id: string = ds.dataSourceId ?? '';
            if (id.includes('step_count')) {
                steps = points.reduce((acc, p) => acc + (p.value?.[0]?.intVal ?? 0), 0);
            } else if (id.includes('distance')) {
                distanceM = points.reduce((acc, p) => acc + (p.value?.[0]?.fpVal ?? 0), 0);
            } else if (id.includes('calories')) {
                calories = points.reduce((acc, p) => acc + (p.value?.[0]?.fpVal ?? 0), 0);
            } else if (id.includes('active_minutes')) {
                activeMin = points.reduce((acc, p) => acc + (p.value?.[0]?.intVal ?? 0), 0);
            }
        }

        if (steps > 0 || distanceM > 0 || activeMin > 0) {
            summary.walk = {
                done: activeMin,
                steps,
                distance: distanceM / 1000,
            };
        }
        if (calories > 0) summary.calories = Math.round(calories);

        if (healthSleepData?.dataPoints && healthSleepData.dataPoints.length > 0) {
            let totalSleepSec = 0;
            for (const point of healthSleepData.dataPoints) {
                const interval = point.sleep?.interval ?? point.exercise?.interval;
                const s = interval?.startTime ? new Date(interval.startTime).getTime() : NaN;
                const e = interval?.endTime ? new Date(interval.endTime).getTime() : NaN;
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

        const data = await this.fetchFitAggregate(
            ['com.google.weight'],
            start.getTime(),
            end.getTime()
        );

        const allPoints: any[] = (data?.bucket ?? [])
            .flatMap((b: any) => (b.dataset ?? []).flatMap((ds: any) => ds.point ?? []));

        if (allPoints.length > 0) {
            const latest = allPoints.reduce((a, b) =>
                BigInt(b.endTimeNanos ?? 0) > BigInt(a.endTimeNanos ?? 0) ? b : a
            );
            return { weight: latest.value?.[0]?.fpVal };
        }
        return null;
    }
}
