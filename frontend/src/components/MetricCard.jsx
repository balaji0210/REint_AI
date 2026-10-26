import React from 'react';

export default function MetricCard({ title, value, unit, subtext, icon: Icon, accentColor }) {
  return (
    <div className="metric-card" style={accentColor ? { borderTop: `3px solid ${accentColor}` } : {}}>
      <div className="metric-header">
        <span className="metric-title">{title}</span>
        {Icon && <Icon size={18} className="metric-icon" />}
      </div>
      <div>
        <span className="metric-value">{value ?? '—'}</span>
        {unit && <span className="metric-unit">{unit}</span>}
      </div>
      {subtext && <div className="metric-subtext">{subtext}</div>}
    </div>
  );
}
