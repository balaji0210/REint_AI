import React from 'react';
import { Wind, Activity, Compass, BarChart3, BookOpen, Sun, Moon } from 'lucide-react';

export default function Header({ activeTab, setActiveTab, theme, onToggleTheme }) {
  const tabs = [
    { id: 'overview', label: '1. Overview', icon: Activity },
    { id: 'explorer', label: '2. Forecast Explorer', icon: Compass },
    { id: 'accuracy', label: '3. Accuracy Analysis', icon: BarChart3 },
    { id: 'methodology', label: '4. Data & Methodology', icon: BookOpen },
  ];

  return (
    <header className="app-header">
      <div className="header-top">
        <div className="brand-section">
          <div className="brand-icon">
            <Wind size={24} color="#ffffff" />
          </div>
          <div>
            <div className="brand-title">UK Wind Power Forecasting & Accuracy Dashboard</div>
            <div className="brand-subtitle">Day-Ahead Purchasing Operations • GB Grid Analytics</div>
          </div>
        </div>

        <div className="header-meta">
          <span className="badge-live">Elexon BMRS Live Stream</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }} className="font-mono">
            Timezone: UTC (GMT)
          </span>

          <button
            type="button"
            className="theme-toggle-btn"
            onClick={onToggleTheme}
            title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
            aria-label="Toggle color theme"
          >
            {theme === 'light' ? (
              <>
                <Moon size={15} style={{ color: 'var(--accent-violet)' }} />
                <span>Dark Mode</span>
              </>
            ) : (
              <>
                <Sun size={15} style={{ color: 'var(--accent-amber)' }} />
                <span>Light Mode</span>
              </>
            )}
          </button>
        </div>
      </div>

      <nav className="nav-tabs" aria-label="Dashboard views">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              className={`nav-tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </nav>
    </header>
  );
}
