import { HealthWeight, DailyHabits, ExerciseLog } from './types';

// Web Client ID verificado
const CLIENT_ID = "1003307358410-o3tbms16qbisurm47vb667plt3c27n1g.apps.googleusercontent.com";
// Adicionado escopo oficial para ler Peso e Medidas Corporais (v4)
const SCOPES = "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly";

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
            token: token,
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

            const callback = (response: any) => {
                if (response.error) {
                    reject(response.error);
                } else {
                    this.saveToken(response.access_token);
                    resolve(response.access_token);
                }
            };

            const client = (window as any).google.accounts.oauth2.initTokenClient({
                client_id: CLIENT_ID,
                scope: SCOPES,
                callback: callback,
            });

            client.requestAccessToken({ prompt: this.accessToken ? '' : 'select_account' });
        });
    }

    private static formatCivilTime(date: Date) {
        const pad = (n: number) => n.toString().padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    }

    private static async fetchV4(dataType: string, startTime: Date, endTime: Date) {
        if (!this.accessToken) await this.authorize();

        const startStr = this.formatCivilTime(startTime);
        const endStr = this.formatCivilTime(endTime);
        
        const filter = `interval.civil_start_time >= "${startStr}" AND interval.civil_start_time <= "${endStr}"`;
        const url = `https://health.googleapis.com/v4/users/me/dataTypes/${dataType}/dataPoints?filter=${encodeURIComponent(filter)}`;

        console.log(`[GoogleHealth] Fetching ${dataType}...`);
        const response = await fetch(url, {
            headers: {
                Authorization: `Bearer ${this.accessToken}`,
                Accept: 'application/json'
            }
        });

        if (!response.ok) {
            console.error(`[GoogleHealth] Error fetching ${dataType}:`, response.status, response.statusText);
            return null;
        }
        const data = await response.json();
        console.log(`[GoogleHealth] Received ${dataType}:`, data);
        return data;
    }

    static async getDailyTelemetry(date: Date): Promise<Partial<ExerciseLog>> {
        const start = new Date(date);
        start.setHours(0, 0, 0, 0);
        const end = new Date(date);
        end.setHours(23, 59, 59, 999);

        const [stepsData, distanceData, caloriesData, sleepData, exerciseData] = await Promise.all([
            this.fetchV4('steps', start, end),
            this.fetchV4('distance', start, end),
            this.fetchV4('calories_burned', start, end),
            this.fetchV4('sleep', start, end),
            this.fetchV4('exercise', start, end)
        ]);
        
        const summary: Partial<ExerciseLog> = {};

        if (stepsData?.dataPoints) {
            summary.walk = summary.walk || { done: 0 };
            summary.walk.steps = stepsData.dataPoints.reduce((acc: number, p: any) => acc + parseInt(p.steps?.count || "0"), 0);
        }

        if (distanceData?.dataPoints) {
            summary.walk = summary.walk || { done: 0 };
            const totalMm = distanceData.dataPoints.reduce((acc: number, p: any) => acc + parseFloat(p.distance?.distanceMillimeters || "0"), 0);
            summary.walk.distance = totalMm / 1000000;
        }

        if (caloriesData?.dataPoints) {
            summary.calories = Math.round(caloriesData.dataPoints.reduce((acc: number, p: any) => acc + parseFloat(p.caloriesBurned?.caloriesKcal || "0"), 0));
        }

        if (exerciseData?.dataPoints) {
            const totalActiveSec = exerciseData.dataPoints.reduce((acc: number, p: any) => {
                const duration = p.exercise?.activeDuration || "0s";
                return acc + parseInt(duration.replace('s', ''));
            }, 0);
            summary.walk = summary.walk || { done: 0 };
            summary.walk.done = Math.round(totalActiveSec / 60);
        }

        if (sleepData?.dataPoints && sleepData.dataPoints.length > 0) {
            let totalSleepSec = 0;
            for (const point of sleepData.dataPoints) {
                const s = new Date(point.sleep.interval.startTime).getTime();
                const e = new Date(point.sleep.interval.endTime).getTime();
                totalSleepSec += (e - s) / 1000;
            }
            summary.sleep = {
                totalMinutes: Math.round(totalSleepSec / 60)
            };
        }

        return summary;
    }

    static async getWeight(date: Date): Promise<Partial<HealthWeight> | null> {
        const start = new Date(date);
        start.setHours(0, 0, 0, 0);
        const end = new Date(date);
        end.setHours(23, 59, 59, 999);

        const data = await this.fetchV4('weight', start, end);
        if (data?.dataPoints && data.dataPoints.length > 0) {
            const latest = data.dataPoints[data.dataPoints.length - 1];
            return {
                weight: latest.weight?.weightKg,
                fatPercentage: latest.weight?.bodyFatPercentage,
                muscleMass: latest.weight?.muscleMassKg
            };
        }
        return null;
    }
}
