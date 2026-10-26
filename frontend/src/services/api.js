/**
 * API service for communicating with the Wind Forecast Dashboard backend.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

async function fetchJson(endpoint, params = {}) {
  const url = new URL(`${API_BASE}${endpoint}`);
  Object.entries(params).forEach(([key, val]) => {
    if (val !== undefined && val !== null && val !== '') {
      url.searchParams.append(key, val);
    }
  });

  const response = await fetch(url.toString(), {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        errorDetail = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail);
      }
    } catch {
      // fallback to status text
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

export const api = {
  getHealth: () => fetchJson('/api/health'),

  getActuals: (start = '2026-01-01', end = '2026-01-31', method = 'hourly_mean') =>
    fetchJson('/api/actuals', { start, end, method }),

  getForecasts: (start = '2026-01-01', end = '2026-01-31', cutoff_time = '09:00', cutoff_days_before = 1) =>
    fetchJson('/api/forecasts', { start, end, cutoff_time, cutoff_days_before }),

  getComparison: (
    start = '2026-01-01',
    end = '2026-01-31',
    cutoff_time = '09:00',
    cutoff_days_before = 1,
    method = 'hourly_mean'
  ) => fetchJson('/api/comparison', { start, end, cutoff_time, cutoff_days_before, method }),

  getAccuracy: (
    start = '2026-01-01',
    end = '2026-01-31',
    cutoff_time = '09:00',
    cutoff_days_before = 1,
    method = 'hourly_mean'
  ) => fetchJson('/api/accuracy', { start, end, cutoff_time, cutoff_days_before, method }),

  getDailyAccuracy: (
    start = '2026-01-01',
    end = '2026-01-31',
    cutoff_time = '09:00',
    cutoff_days_before = 1,
    method = 'hourly_mean'
  ) => fetchJson('/api/daily-accuracy', { start, end, cutoff_time, cutoff_days_before, method }),

  getForecastExplorer: (target, cutoff_time = '09:00', cutoff_days_before = 1) =>
    fetchJson('/api/forecast-explorer', { target, cutoff_time, cutoff_days_before }),

  getMethodology: () => fetchJson('/api/methodology'),
};
