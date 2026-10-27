import React from 'react';
import { Calendar, Clock, RefreshCw, Sliders } from 'lucide-react';

export default function DateControls({
  startDate,
  setStartDate,
  endDate,
  setEndDate,
  cutoffTime,
  setCutoffTime,
  method,
  setMethod,
  onRefresh,
  loading,
}) {
  return (
    <div className="controls-panel">
      <div className="controls-group">
        {/* Date range filter restricted to January 2026 */}
        <div className="control-item">
          <label className="control-label">
            <Calendar size={12} style={{ display: 'inline', marginRight: 4 }} />
            Delivery Start (UTC)
          </label>
          <input
            type="date"
            className="control-input font-mono"
            min="2024-01-01"
            max="2026-12-31"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </div>

        <div className="control-item">
          <label className="control-label">
            <Calendar size={12} style={{ display: 'inline', marginRight: 4 }} />
            Delivery End (UTC)
          </label>
          <input
            type="date"
            className="control-input font-mono"
            min="2024-01-01"
            max="2026-12-31"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>

        {/* Cutoff Time Control */}
        <div className="control-item">
          <label className="control-label">
            <Clock size={12} style={{ display: 'inline', marginRight: 4 }} />
            D-1 Cutoff Time (UTC)
          </label>
          <select
            className="control-select font-mono"
            value={cutoffTime}
            onChange={(e) => setCutoffTime(e.target.value)}
          >
            <option value="09:00">09:00 UTC (GB Day-Ahead Default)</option>
            <option value="07:00">07:00 UTC (Early DA Draft)</option>
            <option value="11:00">11:00 UTC (N2EX Mid-Morning)</option>
            <option value="12:00">12:00 UTC (Midday Cutoff)</option>
            <option value="15:00">15:00 UTC (Afternoon Cutoff)</option>
          </select>
        </div>

        {/* Aggregation method */}
        <div className="control-item">
          <label className="control-label">
            <Sliders size={12} style={{ display: 'inline', marginRight: 4 }} />
            Actuals Aggregation
          </label>
          <select
            className="control-select font-mono"
            value={method}
            onChange={(e) => setMethod(e.target.value)}
          >
            <option value="hourly_mean">Method A: Hourly Mean (Periods 2k-1 & 2k)</option>
            <option value="point_match">Method B: Point Match (:00 only)</option>
          </select>
        </div>
      </div>

      <div>
        <button className="btn-refresh" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Refreshing...' : 'Apply Filters'}
        </button>
      </div>
    </div>
  );
}
