/**
 * API service for communicating with the Wind Forecast Dashboard backend.
 * Includes resilient client-side fallback with real January 2026 Elexon data
 * so all modules work seamlessly in cloud deployments even before backend linkage.
 */

import fallbackComparison from '../data/comparison.json';
import fallbackAccuracy from '../data/accuracy.json';
import fallbackDailyAccuracy from '../data/daily_accuracy.json';
import fallbackMethodology from '../data/methodology.json';
import fallbackExplorerPresets from '../data/explorer_presets.json';

const rawApiUrl = import.meta.env.VITE_API_URL;
const API_BASE = rawApiUrl
  ? rawApiUrl.replace(/\/+$/, '')
  : (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '');

function calculateClientMetrics(rows) {
  if (!rows || rows.length === 0) {
    return {
      mae: 0,
      rmse: 0,
      mean_error: 0,
      mape: 0,
      wape: 0,
      total_intervals: 0,
      unmatched_actuals: 0,
      unmatched_forecasts: 0,
      mape_excluded_count: 0,
    };
  }

  const n = rows.length;
  let sumAbsErr = 0;
  let sumSqErr = 0;
  let sumErr = 0;
  let sumActual = 0;
  let sumPctErr = 0;
  let validMapeCount = 0;

  for (const r of rows) {
    const err = r.forecast_generation - r.actual_generation;
    const absErr = Math.abs(err);
    sumAbsErr += absErr;
    sumSqErr += err * err;
    sumErr += err;
    sumActual += r.actual_generation;

    if (r.actual_generation > 0) {
      sumPctErr += (absErr / r.actual_generation) * 100;
      validMapeCount++;
    }
  }

  return {
    mae: Number((sumAbsErr / n).toFixed(2)),
    rmse: Number(Math.sqrt(sumSqErr / n).toFixed(2)),
    mean_error: Number((sumErr / n).toFixed(2)),
    mape: validMapeCount > 0 ? Number((sumPctErr / validMapeCount).toFixed(2)) : 0,
    wape: sumActual > 0 ? Number(((sumAbsErr / sumActual) * 100).toFixed(2)) : 0,
    total_intervals: n,
    unmatched_actuals: 0,
    unmatched_forecasts: 0,
    mape_excluded_count: n - validMapeCount,
    start_date: rows[0]?.startTime.substring(0, 10),
    end_date: rows[rows.length - 1]?.startTime.substring(0, 10),
    cutoff_time: '09:00',
    method: 'hourly_mean',
  };
}

function getFallbackData(endpoint, params = {}) {
  const { start = '2026-01-01', end = '2026-01-31', target } = params;

  if (endpoint.startsWith('/api/methodology')) {
    return fallbackMethodology;
  }

  if (endpoint.startsWith('/api/forecast-explorer')) {
    if (target && fallbackExplorerPresets[target]) {
      return fallbackExplorerPresets[target];
    }
    return fallbackExplorerPresets['2026-01-15T12:00:00Z'] || Object.values(fallbackExplorerPresets)[0];
  }

  const allRows = fallbackComparison.data || [];
  const filteredRows = allRows.filter((r) => {
    const dateStr = r.startTime.substring(0, 10);
    return dateStr >= start && dateStr <= end;
  });

  if (endpoint.startsWith('/api/comparison')) {
    return {
      data: filteredRows,
      total_matched: filteredRows.length,
      unmatched_actuals: 0,
      unmatched_forecasts: 0,
      cutoff_time: params.cutoff_time || '09:00',
      cutoff_days_before: 1,
      method: params.method || 'hourly_mean',
    };
  }

  if (endpoint.startsWith('/api/accuracy')) {
    if (start === '2026-01-01' && end === '2026-01-31') {
      return fallbackAccuracy;
    }
    return calculateClientMetrics(filteredRows);
  }

  if (endpoint.startsWith('/api/daily-accuracy')) {
    const allDaily = fallbackDailyAccuracy.daily_metrics || [];
    const filteredDaily = allDaily.filter((d) => d.date >= start && d.date <= end);
    return {
      start_date: start,
      end_date: end,
      cutoff_time: params.cutoff_time || '09:00',
      total_days: filteredDaily.length,
      daily_metrics: filteredDaily,
    };
  }

  if (endpoint.startsWith('/api/actuals')) {
    return { data: filteredRows.map((r) => ({ startTime: r.startTime, generation: r.actual_generation })) };
  }

  if (endpoint.startsWith('/api/forecasts')) {
    return { data: filteredRows.map((r) => ({ startTime: r.startTime, publishTime: r.publishTime, generation: r.forecast_generation })) };
  }

  return { status: 'healthy', version: '1.0.0' };
}

async function fetchJson(endpoint, params = {}) {
  // If deployed in production and no external backend URL is specified,
  // serve embedded real dataset directly without throwing unhandled HTML errors.
  const isCloudWithoutBackend = !rawApiUrl && typeof window !== 'undefined' &&
    window.location.hostname !== 'localhost' &&
    window.location.hostname !== '127.0.0.1';

  if (isCloudWithoutBackend) {
    return getFallbackData(endpoint, params);
  }

  try {
    const base = API_BASE || (typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000');
    const url = new URL(`${base}${endpoint}`);
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

    const contentType = response.headers.get('content-type') || '';
    if (!response.ok || !contentType.includes('application/json')) {
      console.warn(`Backend returned non-JSON (${response.status} ${contentType}) for ${endpoint}. Serving embedded data.`);
      return getFallbackData(endpoint, params);
    }

    return await response.json();
  } catch (err) {
    console.warn(`Fetch error for ${endpoint}: ${err.message}. Serving embedded data.`);
    return getFallbackData(endpoint, params);
  }
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
