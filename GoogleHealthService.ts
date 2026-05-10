import { HealthWeight, DailyHabits, ExerciseLog } from './types';

const CLIENT_ID = "1003307358410-8kbah3acif4i0adua051d0icmo8du66i.apps.googleusercontent.com";
const SCOPES = "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly";

export class GoogleHealthService {
    private static accessToken: string | null = null;

    static async authorize() {
        return new Promise<string>((resolve, reject) => {
            if (!(window as any).google) {
                reject(new Error("Google Identity Services not loaded."));
                return;
            }

            const callback = (response: any) => {
                if (response.error) {
                    reject(response.error);
                } else {
                    this.accessToken = response.access_token;
                    resolve(response.access_token);
                }
            };

            const client = (window as any).google.accounts.oauth2.initTokenClient({
                client_id: CLIENT_ID,
                scope: SCOPES,
                callback: callback,
            });

            client.requestAccessToken();
        });
    }

    private static async fetchV4(dataType: string, startTime: Date, endTime: Date) {
        if (!this.accessToken) await this.authorize();

        const filter = `interval.civil_start_time >= "${startTime.toISOString().split('.')[0]}" AND interval.civil_start_time <= "${endTime.toISOString().split('.')[0]}"`;
        const url = `https://health.googleapis.com/v4/users/me/dataTypes/${dataType}/dataPoints?filter=${encodeURIComponent(filter)}`;

        const response = await fetch(url, {
            headers: {
                Authorization: `Bearer ${this.accessToken}`,
                Accept: 'application/json'
            }
        });

        if (!response.ok) return null;
        return await response.json();
    }

    static async getDailyTelemetry(date: Date): Promise<Partial<ExerciseLog>> {
        const start = new Date(date);
        start.setHours(0, 0, 0, 0);
        const end = new Date(date);
        end.setHours(23, 59, 59, 999);

        const exerciseData = await this.fetchV4('exercise', start, end);
        const sleepData = await this.fetchV4('sleep', start, end);
        
        const summary: Partial<ExerciseLog> = {};

        if (exerciseData?.dataPoints) {
            let totalSteps = 0;
            let totalDistance = 0;
            let totalCalories = 0;
            let totalDuration = 0;

            for (const point of exerciseData.dataPoints) {
                const metrics = point.exercise?.metricsSummary;
                if (metrics) {
                    totalSteps += parseInt(metrics.steps || "0");
                    totalDistance += parseFloat(metrics.distanceMillimiters || "0") / 1000000; // to km
                    totalCalories += parseFloat(metrics.caloriesKcal || "0");
                    totalDuration += parseInt(point.exercise.activeDuration?.replace('s', '') || "0");
                }
            }

            if (totalSteps > 0) {
                summary.walk = { 
                    done: Math.round(totalDuration / 60), 
                    steps: totalSteps,
                    distance: totalDistance
                };
                summary.calories = Math.round(totalCalories);
            }
        }

        if (sleepData?.dataPoints && sleepData.dataPoints.length > 0) {
            let totalSleepSec = 0;
            for (const point of sleepData.dataPoints) {
                const start = new Date(point.sleep.interval.startTime).getTime();
                const end = new Date(point.sleep.interval.endTime).getTime();
                totalSleepSec += (end - start) / 1000;
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
                fatPercentage: latest.weight?.bodyFatPercentage
            };
        }
        return null;
    }
}
