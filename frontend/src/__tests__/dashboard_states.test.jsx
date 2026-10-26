import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import OverviewTab from '../pages/OverviewTab';
import AccuracyTab from '../pages/AccuracyTab';
import MetricCard from '../components/MetricCard';
import { Activity } from 'lucide-react';

describe('Frontend Dashboard State & Component Tests', () => {
  describe('OverviewTab States', () => {
    it('renders loading state when loading=true', () => {
      render(<OverviewTab loading={true} comparison={null} accuracy={null} error={null} />);

      const loadingContainer = screen.getByTestId('loading-state');
      expect(loadingContainer).toBeInTheDocument();
      expect(
        screen.getByText(/Loading January 2026 wind outturn and day-ahead forecast data/i)
      ).toBeInTheDocument();
    });

    it('renders empty state when comparison data is empty', () => {
      render(<OverviewTab loading={false} comparison={[]} accuracy={null} error={null} />);

      const emptyContainer = screen.getByTestId('empty-state');
      expect(emptyContainer).toBeInTheDocument();
      expect(
        screen.getByText(/No comparison data found for the selected date range and cutoff/i)
      ).toBeInTheDocument();
    });

    it('renders error state when error is passed', () => {
      const errorMessage = 'Network timeout while querying Elexon BMRS upstream';
      render(
        <OverviewTab
          loading={false}
          comparison={null}
          accuracy={null}
          error={errorMessage}
        />
      );

      const errorContainer = screen.getByTestId('error-state');
      expect(errorContainer).toBeInTheDocument();
      expect(screen.getByText(errorMessage)).toBeInTheDocument();
      expect(screen.getByText(/Error loading dashboard data/i)).toBeInTheDocument();
    });
  });

  describe('AccuracyTab States', () => {
    it('renders loading state when loading=true', () => {
      render(
        <AccuracyTab
          loading={true}
          accuracy={null}
          dailyAccuracy={null}
          comparison={null}
          error={null}
        />
      );

      const loadingContainer = screen.getByTestId('loading-state');
      expect(loadingContainer).toBeInTheDocument();
      expect(
        screen.getByText(/Calculating daily accuracy distributions and error analytics/i)
      ).toBeInTheDocument();
    });

    it('renders empty state when comparison is empty', () => {
      render(
        <AccuracyTab
          loading={false}
          accuracy={null}
          dailyAccuracy={null}
          comparison={[]}
          error={null}
        />
      );

      const emptyContainer = screen.getByTestId('empty-state');
      expect(emptyContainer).toBeInTheDocument();
      expect(
        screen.getByText(/No accuracy data available for the chosen filters/i)
      ).toBeInTheDocument();
    });
  });

  describe('MetricCard Component', () => {
    it('renders metric title, formatted value, unit and subtext correctly', () => {
      render(
        <MetricCard
          title="Average Actual Generation"
          value="11,578"
          unit="MW"
          subtext="Metered wind outturn (FUELHH)"
          icon={Activity}
          accentColor="#06b6d4"
        />
      );

      expect(screen.getByText('Average Actual Generation')).toBeInTheDocument();
      expect(screen.getByText('11,578')).toBeInTheDocument();
      expect(screen.getByText('MW')).toBeInTheDocument();
      expect(screen.getByText('Metered wind outturn (FUELHH)')).toBeInTheDocument();
    });
  });
});
