import React, { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import DateControls from './components/DateControls';
import OverviewTab from './pages/OverviewTab';
import ForecastExplorerTab from './pages/ForecastExplorerTab';
import AccuracyTab from './pages/AccuracyTab';
import MethodologyTab from './pages/MethodologyTab';
import { api } from './services/api';

export default function App() {
  const [theme, setTheme] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('reint_theme') || 'light';
    }
    return 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('reint_theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
  };

  const [activeTab, setActiveTab] = useState('overview');
  const [startDate, setStartDate] = useState('2026-01-01');
  const [endDate, setEndDate] = useState('2026-01-31');
  const [cutoffTime, setCutoffTime] = useState('09:00');
  const [method, setMethod] = useState('hourly_mean');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [accuracy, setAccuracy] = useState(null);
  const [dailyAccuracy, setDailyAccuracy] = useState(null);
  const [comparison, setComparison] = useState([]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [accRes, dailyRes, compRes] = await Promise.all([
        api.getAccuracy(startDate, endDate, cutoffTime, 1, method),
        api.getDailyAccuracy(startDate, endDate, cutoffTime, 1, method),
        api.getComparison(startDate, endDate, cutoffTime, 1, method),
      ]);
      setAccuracy(accRes);
      setDailyAccuracy(dailyRes);
      setComparison(compRes.data || []);
    } catch (err) {
      setError(err.message || 'Failed to fetch dashboard data from backend API');
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate, cutoffTime, method]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <div className="app-container">
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      <main className="main-content">
        {/* Date and cutoff controls shown on Overview, Accuracy, and Methodology */}
        {activeTab !== 'explorer' && (
          <DateControls
            startDate={startDate}
            setStartDate={setStartDate}
            endDate={endDate}
            setEndDate={setEndDate}
            cutoffTime={cutoffTime}
            setCutoffTime={setCutoffTime}
            method={method}
            setMethod={setMethod}
            onRefresh={loadData}
            loading={loading}
          />
        )}

        {/* Tab 1: Overview */}
        {activeTab === 'overview' && (
          <OverviewTab
            accuracy={accuracy}
            comparison={comparison}
            loading={loading}
            error={error}
            startDate={startDate}
            endDate={endDate}
          />
        )}

        {/* Tab 2: Forecast Explorer */}
        {activeTab === 'explorer' && (
          <ForecastExplorerTab cutoffTime={cutoffTime} />
        )}

        {/* Tab 3: Accuracy Analysis */}
        {activeTab === 'accuracy' && (
          <AccuracyTab
            accuracy={accuracy}
            dailyAccuracy={dailyAccuracy}
            comparison={comparison}
            loading={loading}
            error={error}
          />
        )}

        {/* Tab 4: Data & Methodology */}
        {activeTab === 'methodology' && (
          <MethodologyTab
            comparison={comparison}
            accuracy={accuracy}
          />
        )}
      </main>
    </div>
  );
}
