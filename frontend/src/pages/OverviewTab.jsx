import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { Zap, Activity, AlertCircle, Clock, CheckCircle2, Info } from 'lucide-react';
import MetricCard from '../components/MetricCard';

export default function OverviewTab({ accuracy, comparison, loading, error, startDate, endDate }) {
  const formatLoadingPeriod = () => {
    if (!startDate) return 'January 2026';
    try {
      const start = new Date(startDate + 'T00:00:00Z');
      const end = endDate ? new Date(endDate + 'T00:00:00Z') : start;
      const startMonth = start.toLocaleString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });
      const endMonth = end.toLocaleString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });

      if (startMonth === endMonth) {
        return startMonth;
      }
      return `${startMonth} – ${endMonth}`;
    } catch {
      return 'January 2026';
    }
  };

  if (loading) {
    return (
      <div className="state-container" data-testid="loading-state">
        <div className="spinner"></div>
        <p style={{ color: 'var(--text-muted)', fontWeight: 500 }}>
          Loading {formatLoadingPeriod()} wind outturn and day-ahead forecast data...
        </p>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginTop: 4 }}>
          (On initial cold start, the backend may take a few seconds to ingest and align upstream Elexon data)
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-container" data-testid="error-state">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
          <AlertCircle size={18} />
          <span>Error loading dashboard data</span>
        </div>
        <p style={{ marginTop: 6, fontSize: '0.85rem' }}>{error}</p>
      </div>
    );
  }

  if (!comparison || comparison.length === 0) {
    return (
      <div className="state-container" data-testid="empty-state">
        <p style={{ color: 'var(--text-muted)' }}>No comparison data found for the selected date range and cutoff.</p>
      </div>
    );
  }

  // Calculate averages from comparison data if available
  const avgActual = comparison?.length
    ? Math.round(comparison.reduce((acc, row) => acc + row.actual_generation, 0) / comparison.length)
    : null;
  const avgForecast = comparison?.length
    ? Math.round(comparison.reduce((acc, row) => acc + row.forecast_generation, 0) / comparison.length)
    : null;

  // Prepare chart data with formatted labels
  const chartData = (comparison || []).map((row) => ({
    time: row.startTime.replace('T', ' ').substring(5, 16) + ' UTC',
    Actual: row.actual_generation,
    Forecast: row.forecast_generation,
    error: row.error,
  }));

  return (
    <div>
      {/* Important Procurement Shortfall Note */}
      <div className="callout-note">
        <div className="callout-title">
          <Info size={16} />
          Important Note on Procurement Shortfall & Balancing Market Cashout
        </div>
        <p>
          This dashboard strictly evaluates <strong>physical wind generation forecast accuracy</strong> against metered outturn.
          It does <strong>not</strong> compute procurement shortfall or commercial imbalance costs. Calculating shortfall
          requires supplier customer demand profiles, contracted hedging positions, and settlement-period System Buy/Sell Prices (SBP/SSP).
          Wind forecast variance is an input to balancing risk, not a standalone volume shortfall.
        </p>
      </div>

      {/* KPI Cards Grid */}
      <div className="metrics-grid">
        <MetricCard
          title="Avg Actual Generation"
          value={avgActual ? avgActual.toLocaleString() : '—'}
          unit="MW"
          subtext="Metered wind outturn (FUELHH)"
          icon={Activity}
          accentColor="var(--accent-cyan)"
        />
        <MetricCard
          title="Avg DA Forecast"
          value={avgForecast ? avgForecast.toLocaleString() : '—'}
          unit="MW"
          subtext={`Selected prior to ${accuracy?.cutoff_time || '09:00'} UTC`}
          icon={Zap}
          accentColor="var(--accent-amber)"
        />
        <MetricCard
          title="Mean Absolute Error (MAE)"
          value={accuracy?.mae ? accuracy.mae.toLocaleString() : '—'}
          unit="MW"
          subtext="Average absolute forecast gap"
          icon={AlertCircle}
          accentColor="var(--accent-rose)"
        />
        <MetricCard
          title="Root Mean Sq Error (RMSE)"
          value={accuracy?.rmse ? accuracy.rmse.toLocaleString() : '—'}
          unit="MW"
          subtext="Penalizes large extreme deviations"
          icon={AlertCircle}
          accentColor="var(--accent-violet)"
        />
        <MetricCard
          title="Mean Error (Bias)"
          value={accuracy?.mean_error ? (accuracy.mean_error > 0 ? `+${accuracy.mean_error.toLocaleString()}` : accuracy.mean_error.toLocaleString()) : '—'}
          unit="MW"
          subtext={accuracy?.mean_error > 0 ? 'Over-forecasting bias' : 'Under-forecasting bias'}
          icon={Clock}
          accentColor={accuracy?.mean_error > 0 ? 'var(--accent-amber)' : 'var(--accent-blue)'}
        />
        <MetricCard
          title="Matched Delivery Hours"
          value={accuracy?.n_matched ?? 0}
          unit="hrs"
          subtext="Complete hourly pairs evaluated"
          icon={CheckCircle2}
          accentColor="var(--accent-emerald)"
        />
      </div>

      {/* Main Time-Series Chart */}
      <div className="dashboard-card">
        <div className="card-header">
          <div>
            <div className="card-title">
              <Zap size={18} color="var(--accent-cyan)" />
              Day-Ahead Wind Forecast vs Actual Generation (January 2026)
            </div>
            <div className="card-subtitle">
              Comparing locked Day-Ahead forecasts (at or before {accuracy?.cutoff_time || '09:00'} UTC on D-1) against metered outturn.
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.8rem' }} className="font-mono">
            <span style={{ color: 'var(--accent-cyan)' }}>● Actuals (FUELHH)</span>
            <span style={{ color: 'var(--accent-amber)' }}>● Day-Ahead (WINDFOR)</span>
          </div>
        </div>

        <div className="chart-wrapper">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 25, left: 10, bottom: 25 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
              <XAxis
                dataKey="time"
                stroke="var(--text-dim)"
                tick={{ fontSize: 11 }}
                interval={Math.max(1, Math.floor(chartData.length / 12))}
                angle={-20}
                textAnchor="end"
              />
              <YAxis
                stroke="var(--text-dim)"
                tick={{ fontSize: 11 }}
                tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
                unit=" MW"
                domain={['auto', 'auto']}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--tooltip-bg)',
                  borderColor: 'var(--border-color)',
                  borderRadius: '8px',
                  color: 'var(--tooltip-text)',
                  fontSize: '0.8rem',
                }}
                formatter={(val, name) => [`${val.toLocaleString()} MW`, name]}
                labelFormatter={(lbl) => `Delivery: ${lbl}`}
              />
              <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: '0.8rem' }} />
              <Line
                type="monotone"
                dataKey="Actual"
                stroke="var(--accent-cyan)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 5 }}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="Forecast"
                stroke="var(--accent-amber)"
                strokeWidth={2}
                strokeDasharray="4 2"
                dot={false}
                activeDot={{ r: 5 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
