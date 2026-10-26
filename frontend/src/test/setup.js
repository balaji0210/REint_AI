import '@testing-library/jest-dom';

// Mock ResizeObserver for Recharts responsive containers
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
