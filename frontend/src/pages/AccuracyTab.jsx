import React from 'react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { BarChart3, AlertTriangle, Layers, Clock, TrendingUp } from 'lucide-react';
import MetricCard from '../components/MetricCard';

export default function AccuracyTab({ accuracy, dailyAccuracy, comparison, loading, error }) {
  if (loading) {
    return (
      <div className="state-container" data-testid="loading-state">
        <div className="spinner"></div>
        <p style={{ color: 'var(--text-muted)' }}>Calculating daily accuracy distributions and error analytics...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-container" data-testid="error-state">
        <p>{error}</p>
      </div>
    );
  }

  if (!comparison || comparison.length === 0) {
    return (
      <div className="state-container" data-testid="empty-state">
        <p style={{ color: 'var(--text-muted)' }}>No accuracy data available for the chosen filters.</p>
      </div>
    );
  }

  // 1. Error over time chart data
  const errorTimeData = (comparison || []).map((row) => ({
    time: row.startTime.replace('T', ' ').substring(5, 16) + ' UTC',
    error: row.error,
    abs_error: row.absolute_error,
  }));

  // 2. Daily MAE / RMSE chart data
  const dailyChartData = (dailyAccuracy?.daily_metrics || []).map((d) => ({
    date: d.date.substring(5),
    MAE: d.mae,
    RMSE: d.rmse,
    Bias: d.mean_error,
  }));

  // 3. Top 10 largest-error intervals
  const top10Errors = comparison ? [...comparison].sort((a, b) => b.absolute_error - a.absolute_error).slice(0, 10) : [];

  return (
    <div>
      {/* Matched vs Unmatched Diagnostics */}
      <div className="metrics-grid">
        <MetricCard
          title="Overall MAE"
          value={accuracy?.mae ? `${accuracy.mae.toLocaleString()}` : '—'}
          unit="MW"
          subtext="Mean Absolute Error across month"
          icon={BarChart3}
          accentColor="var(--accent-cyan)"
        />
        <MetricCard
          title="Overall RMSE"
          value={accuracy?.rmse ? `${accuracy.rmse.toLocaleString()}` : '—'}
          unit="MW"
          subtext="Root Mean Squared Error"
          icon={TrendingUp}
          accentColor="var(--accent-violet)"
        />
        <MetricCard
          title="Overall Mean Bias"
          value={accuracy?.mean_error ? `${accuracy.mean_error > 0 ? '+' : ''}${accuracy.mean_error.toLocaleString()}` : '—'}
          unit="MW"
          subtext="Positive = Day-Ahead over-forecast"
          icon={Clock}
          accentColor={accuracy?.mean_error > 0 ? 'var(--accent-amber)' : 'var(--accent-emerald)'}
        />
        <MetricCard
          title="Matched Hourly Intervals"
          value={accuracy?.n_matched ?? 0}
          unit="hrs"
          subtext={`Unmatched actuals: ${accuracy?.unmatched_actuals ?? 0}`}
          icon={Layers}
          accentColor="var(--accent-emerald)"
        />
        <MetricCard
          title="Unmatched Forecast Runs"
          value={accuracy?.unmatched_forecasts ?? 0}
          unit="intervals"
          subtext="Forecasts outside delivery window"
          icon={Layers}
          accentColor="var(--text-dim)"
        />
      </div>

      {/* Daily MAE / RMSE Bar Chart */}
      <div className="dashboard-card">
        <div className="card-header">
          <div>
            <div className="card-title">
              <BarChart3 size={18} color="var(--accent-cyan)" />
              Daily Forecast Error: MAE & RMSE Breakdown (January 2026)
            </div>
            <div className="card-subtitle">
              Daily average absolute errors (MAE) and root mean square error (RMSE) in Megawatts.
            </div>
          </div>
          <div style={{ display: 'flex', gap: '1rem', fontSize: '0.8rem' }} className="font-mono">
            <span style={{ color: 'var(--accent-cyan)' }}>■ Daily MAE</span>
            <span style={{ color: 'var(--accent-violet)' }}>■ Daily RMSE</span>
          </div>
        </div>

        <div className="chart-wrapper">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={dailyChartData} margin={{ top: 10, right: 25, left: 10, bottom: 25 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
              <XAxis dataKey="date" stroke="var(--text-dim)" tick={{ fontSize: 11 }} />
              <YAxis stroke="var(--text-dim)" tick={{ fontSize: 11 }} unit=" MW" />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--tooltip-bg)',
                  borderColor: 'var(--border-color)',
                  borderRadius: '8px',
                  color: 'var(--tooltip-text)',
                  fontSize: '0.8rem',
                }}
                formatter={(val, name) => [`${val.toLocaleString()} MW`, name]}
                labelFormatter={(lbl) => `Jan ${lbl}`}
              />
              <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: '0.8rem' }} />
              <Bar dataKey="MAE" fill="var(--accent-cyan)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="RMSE" fill="var(--accent-violet)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Hourly Error Over Time Chart */}
      <div className="dashboard-card">
        <div className="card-header">
          <div>
            <div className="card-title">
              <TrendingUp size={18} color="var(--accent-amber)" />
              Hourly Forecast Error (F - A) Over Time
            </div>
            <div className="card-subtitle">
              Positive values indicate Day-Ahead over-forecast (surplus generation expected); negative values indicate under-forecast.
            </div>
          </div>
        </div>

        <div className="chart-wrapper">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={errorTimeData} margin={{ top: 10, right: 25, left: 10, bottom: 25 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
              <XAxis
                dataKey="time"
                stroke="var(--text-dim)"
                tick={{ fontSize: 11 }}
                interval={Math.max(1, Math.floor(errorTimeData.length / 12))}
                angle={-20}
                textAnchor="end"
              />
              <YAxis stroke="var(--text-dim)" tick={{ fontSize: 11 }} unit=" MW" />
              <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--tooltip-bg)',
                  borderColor: 'var(--border-color)',
                  borderRadius: '8px',
                  color: 'var(--tooltip-text)',
                  fontSize: '0.8rem',
                }}
                formatter={(val) => [`${val.toLocaleString()} MW`, 'Error (F - A)']}
              />
              <Line
                type="monotone"
                dataKey="error"
                stroke="var(--accent-amber)"
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Top 10 Largest-Error Intervals Table */}
      <div className="dashboard-card">
        <div className="card-header">
          <div>
            <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <AlertTriangle size={18} color="var(--accent-rose)" />
              Top 10 Largest Forecast Error Delivery Hours
            </div>
            <div className="card-subtitle">
              The highest absolute discrepancy intervals (|F - A|) where day-ahead purchasing risk was greatest.
            </div>
          </div>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Delivery Hour (UTC)</th>
                <th>Selected Forecast (MW)</th>
                <th>Actual Outturn (MW)</th>
                <th>Error (F - A) (MW)</th>
                <th>Absolute Error (MW)</th>
                <th>Lead Time</th>
                <th>Publish Time (UTC)</th>
              </tr>
            </thead>
            <tbody>
              {top10Errors.map((row, idx) => (
                <tr key={idx}>
                  <td className="font-mono" style={{ fontWeight: 600 }}>
                    {row.startTime.replace('T', ' ').substring(0, 16)} UTC
                  </td>
                  <td className="font-mono">{row.forecast_generation.toLocaleString()} MW</td>
                  <td className="font-mono">{row.actual_generation.toLocaleString()} MW</td>
                  <td
                    className="font-mono"
                    style={{
                      color: row.error > 0 ? 'var(--accent-amber)' : 'var(--accent-blue)',
                      fontWeight: 600,
                    }}
                  >
                    {row.error > 0 ? `+${row.error.toLocaleString()}` : row.error.toLocaleString()} MW
                  </td>
                  <td className="font-mono" style={{ color: 'var(--accent-rose)', fontWeight: 700 }}>
                    {row.absolute_error.toLocaleString()} MW
                  </td>
                  <td className="font-mono">{row.lead_time_hours}h</td>
                  <td className="font-mono" style={{ color: 'var(--text-dim)', fontSize: '0.75rem' }}>
                    {row.publishTime.replace('T', ' ').substring(0, 16)} UTC
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
