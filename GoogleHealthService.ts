import { HealthWeight, ExerciseLog } from './types';

const CLIENT_ID = "1003307358410-o3tbms16qbisurm47vb667plt3c27n1g.apps.googleusercontent.com";

// Health Connect v4: sleep only (exercise/weight use Google Fit — Health Connect REST requires Android-native auth)
// Google Fit: steps, distance, calories, active minutes, weight
const SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.body.read",
].join(" ");

export class GoogleHealthService {
    private static accessToken: string | null = null;
    private static tokenExpiry: number = 0;

    private static loadSavedToken() {
        const saved = localStorage.getItem('hermes_google_health_token');
        if (saved) {
            const { token, expiry } = JSON.parse(saved);
            if (Date.now() < expiry) {
                this.accessToken = token;
                this.tokenExpiry = expiry;
                return true;
            }
        }
        return false;
    }

    private static saveToken(token: string) {
        this.accessToken = token;
        this.tokenExpiry = Date.now() + (55 * 60 * 1000);
        localStorage.setItem('hermes_google_health_token', JSON.stringify({
            token,
            expiry: this.tokenExpiry
        }));
    }

    static async authorize() {
        if (this.loadSavedToken()) {
            return this.accessToken!;
        }

        return new Promise<string>((resolve, reject) => {
            if (!(window as any).google) {
                reject(new Error("Google Identity Services not loaded."));
                return;
            }

            const client = (window as any).google.accounts.oauth2.initTokenClient({
                client_id: CLIENT_ID,
                scope: SCOPES,
                callback: (response: any) => {
                    if (response.error) reject(response.error);
                    else {
                        this.saveToken(response.access_token);
                        resolve(response.access_token);
                    }
                },
            });

            client.requestAccessToken({ prompt: 'consent' });
        });
    }

    private static formatCivilTime(date: Date) {
        const pad = (n: number) => n.toString().padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    }

    // Health Connect v4 — used only for sleep
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

    // Google Fit aggregate — exercise, steps, distance, calories, weight
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
            this.fetchHealthV4('sleep', start, end),
        ]);

        const summary: Partial<ExerciseLog> = {};

        // Parse Google Fit data
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
                distance: distanceM / 1000,  // meters → km
            };
        }
        if (calories > 0) summary.calories = Math.round(calories);

        // Parse Health Connect sleep
        if (sleepData?.dataPoints && sleepData.dataPoints.length > 0) {
            let totalSleepSec = 0;
            for (const point of sleepData.dataPoints) {
                const interval = point.sleep?.interval ?? point.exercise?.interval;
                const s = interval?.startTime ? new Date(interval.startTime).getTime() : NaN;
                const e = interval?.endTime ? new Date(interval.endTime).getTime() : NaN;
                if (!isNaN(s) && !isNaN(e)) totalSleepSec += (e - s) / 1000;
            }
            if (totalSleepSec > 0) {
                summary.sleep = { totalMinutes: Math.round(totalSleepSec / 60) };
            }
        }

        return summary;
    }

    static async getWeight(date: Date): Promise<Partial<HealthWeight> | null> {
        // Search last 30 days — weight isn't recorded daily, take the most recent entry
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
            // Take the most recent point by endTimeNanos
            const latest = allPoints.reduce((a, b) =>
                BigInt(b.endTimeNanos ?? 0) > BigInt(a.endTimeNanos ?? 0) ? b : a
            );
            return { weight: latest.value?.[0]?.fpVal };
        }
        return null;
    }
}
