import React, { useState } from 'react';
import { BookOpen, ShieldAlert, Database, Layers, Calculator, ChevronLeft, ChevronRight, CheckCircle2 } from 'lucide-react';

export default function MethodologyTab({ comparison, accuracy }) {
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 20;

  const totalRecords = comparison?.length || 0;
  const totalPages = Math.ceil(totalRecords / pageSize);
  const startIndex = (currentPage - 1) * pageSize;
  const currentRecords = (comparison || []).slice(startIndex, startIndex + pageSize);

  return (
    <div>
      {/* Shortfall & Imbalance Note */}
      <div className="callout-note" style={{ borderLeftColor: 'var(--accent-rose)' }}>
        <div className="callout-title" style={{ color: 'var(--accent-rose)' }}>
          <ShieldAlert size={18} />
          Commercial Scope: Why We Do NOT Compute Procurement Shortfall
        </div>
        <p style={{ marginTop: '0.4rem' }}>
          This analytics platform explicitly evaluates <strong>GB grid-level wind power forecasting accuracy</strong>.
          We do <strong>not</strong> claim to calculate an energy utility's commercial procurement shortfall or imbalance cashout costs.
          In competitive energy trading:
        </p>
        <ul style={{ marginTop: '0.4rem', marginLeft: '1.25rem', lineHeight: '1.6' }}>
          <li>
            <strong>Demand Coupling</strong>: A physical shortfall only exists when generation falls short of customer demand and bilateral purchase contracts. No demand or trade portfolio data is available in BMRS public feeds.
          </li>
          <li>
            <strong>Cashout Mechanism</strong>: Imbalance settlement under BSC Section T requires half-hourly System Buy/Sell Prices (SBP/SSP) applied to net portfolio imbalance volumes. Wind forecast deviation is an exposure driver, not a financial penalty on its own.
          </li>
        </ul>
      </div>

      {/* Grid of Methodology Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.25rem', marginBottom: '1.5rem' }}>
        {/* Cutoff Rule */}
        <div className="dashboard-card" style={{ marginBottom: 0 }}>
          <div className="card-title" style={{ marginBottom: '0.75rem', color: 'var(--accent-amber)' }}>
            <Calculator size={18} />
            Decision-Cutoff Rule (09:00 UTC D-1)
          </div>
          <p style={{ fontSize: '0.825rem', color: 'var(--text-muted)', lineHeight: '1.6' }}>
            In Great Britain, the primary exchange day-ahead auction (EPEX SPOT GB Day-Ahead) operates with a gate closure of <strong>09:20 UK local time</strong> (09:00 internal decision freeze).
            For any delivery day D, the purchasing desk must lock physical wind generation forecasts at or before <strong>09:00 UTC on D-1</strong>.
          </p>
          <div style={{ marginTop: '0.75rem', padding: '0.75rem', background: 'rgba(15, 23, 42, 0.7)', borderRadius: '6px', fontSize: '0.75rem' }} className="font-mono">
            T_cutoff = (Delivery_Date - 1 day) @ 09:00 UTC<br />
            Selected = argmax(publishTime &lt;= T_cutoff)<br />
            Lead Time: 15.0h (delivery 00:00) to 38.0h (delivery 23:00)
          </div>
        </div>

        {/* Data Sources */}
        <div className="dashboard-card" style={{ marginBottom: 0 }}>
          <div className="card-title" style={{ marginBottom: '0.75rem', color: 'var(--accent-cyan)' }}>
            <Database size={18} />
            BMRS Data Feeds & Resolution
          </div>
          <ul style={{ fontSize: '0.825rem', color: 'var(--text-muted)', lineHeight: '1.6', listStyle: 'none' }}>
            <li>
              <strong>FUELHH (Actuals)</strong>: Half-hourly settlement outturn generation by fuel type. Filtered strictly for <code>fuelType == 'WIND'</code>. Queried via <code>settlementDateFrom/To</code> to capture period 48 cleanly.
            </li>
            <li style={{ marginTop: '0.5rem' }}>
              <strong>WINDFOR (Forecasts)</strong>: National Grid ESO/NESO wind generation forecasts published multiple times daily at hourly cadence (:00).
            </li>
            <li style={{ marginTop: '0.5rem' }}>
              <strong>Resolution Harmonization</strong>: Method A (hourly mean of periods 2k-1 and 2k) is used to match hourly forecasts without inventing non-existent half-hourly data.
            </li>
          </ul>
        </div>

        {/* Metric Definitions */}
        <div className="dashboard-card" style={{ marginBottom: 0 }}>
          <div className="card-title" style={{ marginBottom: '0.75rem', color: 'var(--accent-violet)' }}>
            <Layers size={18} />
            Accuracy Metric Formulas & Units
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: '1.6' }}>
            <div><strong>MAE (MW)</strong>: (1/N) * &Sigma; |Forecast - Actual|</div>
            <div><strong>RMSE (MW)</strong>: &radic;((1/N) * &Sigma; (Forecast - Actual)&sup2;)</div>
            <div><strong>Mean Error / Bias (MW)</strong>: (1/N) * &Sigma; (Forecast - Actual)</div>
            <div><strong>MAPE (%)</strong>: Excludes Actual == 0 to prevent division by zero.</div>
            <div><strong>WAPE (%)</strong>: &Sigma; |Forecast - Actual| / &Sigma; Actual * 100</div>
          </div>
        </div>
      </div>

      {/* Paginated Verification Table */}
      <div className="dashboard-card">
        <div className="card-header">
          <div>
            <div className="card-title">Settlement Verification Table (Full January 2026 Audit)</div>
            <div className="card-subtitle">
              Hour-by-hour audit of selected day-ahead forecasts against settled actual outturn ({totalRecords} intervals).
            </div>
          </div>
          <div className="badge-tag badge-neutral font-mono">
            Page {currentPage} of {totalPages || 1}
          </div>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Delivery Hour (UTC)</th>
                <th>Selected Forecast</th>
                <th>Actual Outturn</th>
                <th>Error (F - A)</th>
                <th>Abs Error</th>
                <th>Lead Time</th>
                <th>Cutoff Deadline</th>
                <th>Publish Time (UTC)</th>
              </tr>
            </thead>
            <tbody>
              {currentRecords.map((row, idx) => (
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
                    }}
                  >
                    {row.error > 0 ? `+${row.error.toLocaleString()}` : row.error.toLocaleString()} MW
                  </td>
                  <td className="font-mono" style={{ fontWeight: 600 }}>
                    {row.absolute_error.toLocaleString()} MW
                  </td>
                  <td className="font-mono">{row.lead_time_hours}h</td>
                  <td className="font-mono" style={{ color: 'var(--text-dim)', fontSize: '0.75rem' }}>
                    {row.cutoff_time.replace('T', ' ').substring(0, 16)} UTC
                  </td>
                  <td className="font-mono" style={{ color: 'var(--text-dim)', fontSize: '0.75rem' }}>
                    {row.publishTime.replace('T', ' ').substring(0, 16)} UTC
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls */}
        <div className="pagination-container">
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Showing intervals {startIndex + 1} to {Math.min(startIndex + pageSize, totalRecords)} of {totalRecords}
          </div>
          <div className="pagination-controls">
            <button
              className="btn-page"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
            >
              <ChevronLeft size={14} style={{ display: 'inline', verticalAlign: 'middle' }} /> Previous
            </button>
            <button
              className="btn-page"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage >= totalPages}
            >
              Next <ChevronRight size={14} style={{ display: 'inline', verticalAlign: 'middle' }} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
