import React, { useState, useEffect } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { Compass, CheckCircle2, XCircle, AlertCircle, Clock, Zap, Activity } from 'lucide-react';
import { api } from '../services/api';
import MetricCard from '../components/MetricCard';

export default function ForecastExplorerTab({ cutoffTime }) {
  const [targetIso, setTargetIso] = useState('2026-01-15T12:00:00Z');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Quick preset targets in January 2026
  const presetTargets = [
    { label: 'Jan 01 12:00 (Month Start)', value: '2026-01-01T12:00:00Z' },
    { label: 'Jan 10 18:00 (High Wind)', value: '2026-01-10T18:00:00Z' },
    { label: 'Jan 15 12:00 (Mid Month)', value: '2026-01-15T12:00:00Z' },
    { label: 'Jan 22 08:00 (Morning Peak)', value: '2026-01-22T08:00:00Z' },
    { label: 'Jan 31 15:00 (Month End)', value: '2026-01-31T15:00:00Z' },
  ];

  const fetchExplorerData = async (target) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getForecastExplorer(target, cutoffTime, 1);
      setData(res);
    } catch (err) {
      setError(err.message || 'Failed to fetch forecast progression');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExplorerData(targetIso);
  }, [targetIso, cutoffTime]);

  const chartData = (data?.forecasts || []).map((f) => ({
    publish: f.publishTime.replace('T', ' ').substring(5, 16) + ' UTC',
    generation: f.generation,
    lead_time: f.lead_time_hours,
    isSelected: f.is_selected,
    isBefore: f.is_before_cutoff,
  }));

  const selectedForecast = data?.forecasts?.find((f) => f.is_selected);
  const errorVal =
    data?.actual_generation !== null && selectedForecast
      ? Math.round(selectedForecast.generation - data.actual_generation)
      : null;

  return (
    <div>
      {/* Target Selector Bar */}
      <div className="controls-panel">
        <div className="controls-group">
          <div className="control-item">
            <label className="control-label">Target Delivery Interval (UTC)</label>
            <input
              type="text"
              className="control-input font-mono"
              style={{ width: '260px' }}
              value={targetIso}
              onChange={(e) => setTargetIso(e.target.value)}
              placeholder="YYYY-MM-DDTHH:MM:SSZ"
            />
          </div>

          <div className="control-item">
            <label className="control-label">Quick Presets (Jan 2026)</label>
            <select
              className="control-select font-mono"
              value={targetIso}
              onChange={(e) => setTargetIso(e.target.value)}
            >
              {presetTargets.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <button
            className="btn-refresh"
            onClick={() => fetchExplorerData(targetIso)}
            disabled={loading}
          >
            {loading ? 'Inspecting...' : 'Inspect Interval'}
          </button>
        </div>
      </div>

      {loading && (
        <div className="state-container">
          <div className="spinner"></div>
          <p style={{ color: 'var(--text-muted)' }}>Retrieving all published forecasts for {targetIso}...</p>
        </div>
      )}

      {error && (
        <div className="error-container">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
            <AlertCircle size={18} />
            <span>Inspection Error</span>
          </div>
          <p style={{ marginTop: 6, fontSize: '0.85rem' }}>{error}</p>
        </div>
      )}

      {data && !loading && (
        <>
          {/* Target Interval Summary Cards */}
          <div className="metrics-grid">
            <MetricCard
              title="Target Delivery Interval"
              value={data.target_startTime.replace('T', ' ').substring(0, 16)}
              unit="UTC"
              subtext="Settlement delivery hour"
              icon={Compass}
              accentColor="var(--accent-cyan)"
            />
            <MetricCard
              title="Actual Outturn Generation"
              value={data.actual_generation ? data.actual_generation.toLocaleString() : 'N/A'}
              unit="MW"
              subtext="Metered wind outturn (FUELHH)"
              icon={Activity}
              accentColor="var(--accent-emerald)"
            />
            <MetricCard
              title="Selected Day-Ahead Forecast"
              value={selectedForecast ? selectedForecast.generation.toLocaleString() : 'N/A'}
              unit="MW"
              subtext={`Locked at ${cutoffTime} UTC on D-1`}
              icon={Zap}
              accentColor="var(--accent-amber)"
            />
            <MetricCard
              title="Forecast Error (F - A)"
              value={errorVal !== null ? (errorVal > 0 ? `+${errorVal.toLocaleString()}` : errorVal.toLocaleString()) : '—'}
              unit="MW"
              subtext={errorVal > 0 ? 'Over-forecasted' : 'Under-forecasted'}
              icon={Clock}
              accentColor={errorVal > 0 ? 'var(--accent-rose)' : 'var(--accent-blue)'}
            />
            <MetricCard
              title="Total Published Revisions"
              value={data.total_forecasts}
              unit="runs"
              subtext="Published updates for this interval"
              icon={Clock}
              accentColor="var(--accent-violet)"
            />
          </div>

          {/* Forecast Evolution Chart */}
          <div className="dashboard-card">
            <div className="card-header">
              <div>
                <div className="card-title">
                  <Compass size={18} color="var(--accent-amber)" />
                  Forecast Evolution Towards Delivery: {targetIso}
                </div>
                <div className="card-subtitle">
                  Visualizing how the forecast changed with each publication batch. Red dashed line indicates the {cutoffTime} UTC D-1 decision gate.
                </div>
              </div>
            </div>

            <div className="chart-wrapper">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 25 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(55, 65, 81, 0.4)" vertical={false} />
                  <XAxis
                    dataKey="publish"
                    stroke="var(--text-dim)"
                    tick={{ fontSize: 11 }}
                    angle={-20}
                    textAnchor="end"
                  />
                  <YAxis
                    stroke="var(--text-dim)"
                    tick={{ fontSize: 11 }}
                    unit=" MW"
                    domain={['auto', 'auto']}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'rgba(15, 23, 42, 0.95)',
                      borderColor: 'var(--border-color)',
                      borderRadius: '8px',
                      color: '#fff',
                      fontSize: '0.8rem',
                    }}
                    formatter={(val, name, item) => [
                      `${val.toLocaleString()} MW (Lead: ${item.payload.lead_time}h)`,
                      'Forecast',
                    ]}
                    labelFormatter={(lbl) => `Published: ${lbl}`}
                  />
                  {data.actual_generation && (
                    <ReferenceLine
                      y={data.actual_generation}
                      stroke="var(--accent-emerald)"
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      label={{
                        value: `Actual Outturn: ${data.actual_generation.toLocaleString()} MW`,
                        fill: 'var(--accent-emerald)',
                        position: 'top',
                        fontSize: 12,
                      }}
                    />
                  )}
                  <Line
                    type="stepAfter"
                    dataKey="generation"
                    stroke="var(--accent-amber)"
                    strokeWidth={2}
                    dot={(props) => {
                      const { cx, cy, payload } = props;
                      if (payload.isSelected) {
                        return (
                          <circle
                            key={`dot-${cx}`}
                            cx={cx}
                            cy={cy}
                            r={7}
                            fill="var(--accent-cyan)"
                            stroke="#fff"
                            strokeWidth={2}
                          />
                        );
                      }
                      return (
                        <circle
                          key={`dot-${cx}`}
                          cx={cx}
                          cy={cy}
                          r={3}
                          fill={payload.isBefore ? 'var(--accent-amber)' : 'var(--text-dim)'}
                        />
                      );
                    }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Table of All Forecasts for this interval */}
          <div className="dashboard-card">
            <div className="card-header">
              <div>
                <div className="card-title">All Published Forecast Revisions for this Target Interval</div>
                <div className="card-subtitle">
                  The cutoff rule selects the latest revision published before {cutoffTime} UTC on D-1 (highlighted in cyan).
                </div>
              </div>
            </div>

            <div className="table-responsive">
              <data-table className="data-table">
                <thead>
                  <tr>
                    <th>Publication Time (UTC)</th>
                    <th>Lead Time (Hours)</th>
                    <th>Forecast Generation (MW)</th>
                    <th>Cutoff Status</th>
                    <th>Selection Action</th>
                  </tr>
                </thead>
                <tbody>
                  {data.forecasts.map((f, idx) => (
                    <tr key={idx} className={f.is_selected ? 'row-selected' : ''}>
                      <td className="font-mono">
                        {f.publishTime.replace('T', ' ').substring(0, 19)} UTC
                      </td>
                      <td className="font-mono">
                        {f.lead_time_hours > 0 ? `+${f.lead_time_hours}h` : `${f.lead_time_hours}h`}
                      </td>
                      <td className="font-mono" style={{ fontWeight: 600 }}>
                        {f.generation.toLocaleString()} MW
                      </td>
                      <td>
                        {f.is_before_cutoff ? (
                          <span className="badge-tag badge-success">Before Cutoff</span>
                        ) : (
                          <span className="badge-tag badge-danger">Post-Cutoff (Excluded)</span>
                        )}
                      </td>
                      <td>
                        {f.is_selected ? (
                          <span className="badge-tag badge-success" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <CheckCircle2 size={12} /> Selected Day-Ahead Forecast
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-dim)', fontSize: '0.75rem' }}>
                            {f.is_before_cutoff ? 'Superseded by later pre-cutoff run' : 'Excluded by decision cutoff'}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </data-table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
