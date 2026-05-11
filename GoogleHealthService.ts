import { HealthWeight, ExerciseLog } from './types';

const CLIENT_ID = "1003307358410-o3tbms16qbisurm47vb667plt3c27n1g.apps.googleusercontent.com";
const TOKEN_STORAGE_KEY = 'hermes_google_health_token';

// Google Fit: steps, distance, calories, active minutes, weight, sleep sessions.
const SCOPES = [
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

    // Google Fit aggregate: exercise, steps, distance, calories, weight.
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

    static async getDailyTelemetry(date: Date): Promise<Partial<ExerciseLog>> {
        const start = new Date(date);
        start.setHours(0, 0, 0, 0);
        const end = new Date(date);
        end.setHours(23, 59, 59, 999);

        const [fitData, sleepData] = await Promise.all([
            this.fetchFitAggregate(
                ['com.google.step_count.delta', 'com.google.distance.delta', 'com.google.calories.expended', 'com.google.active_minutes'],
                start.getTime(),
                end.getTime()
            ),
            this.fetchFitSleepSessions(start, end),
        ]);

        const summary: Partial<ExerciseLog> = {};

        // Parse Google Fit activity data.
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

        const sleepSessions: any[] = sleepData?.session ?? [];
        const totalSleepMs = sleepSessions.reduce((acc, session) => {
            const startMs = Number(session.startTimeMillis);
            const endMs = Number(session.endTimeMillis);
            return Number.isFinite(startMs) && Number.isFinite(endMs) && endMs > startMs
                ? acc + (endMs - startMs)
                : acc;
        }, 0);

        if (totalSleepMs > 0) {
            summary.sleep = { totalMinutes: Math.round(totalSleepMs / 60000) };
        }

        return summary;
    }

    static async getWeight(date: Date): Promise<Partial<HealthWeight> | null> {
        // Search last 30 days: weight is not recorded daily, so take the most recent entry.
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
