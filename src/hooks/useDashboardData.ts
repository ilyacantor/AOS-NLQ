import { useState, useEffect, useCallback, useRef } from 'react';
import {
  DashboardConfig,
  TileConfig,
  TileData,
  InsightItem,
  TrendData,
  SparklineDataPoint,
  StatusType,
  isKPITile,
  isChartTile,
  isInsightsTile,
} from '../types/dashboard';

/**
 * Static CFO dashboard data - precomputed for instant load
 * This avoids 10+ API calls that each take 2-3 seconds
 */
const STATIC_CFO_DATA: Record<string, TileData> = {
  'kpi-revenue': {
    value: 48.2,
    formattedValue: '$48.2M',
    trend: { direction: 'up', percentChange: 18, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Jan', value: 3.8 }, { period: 'Feb', value: 3.9 }, { period: 'Mar', value: 4.0 },
      { period: 'Apr', value: 4.1 }, { period: 'May', value: 4.0 }, { period: 'Jun', value: 4.2 },
      { period: 'Jul', value: 4.1 }, { period: 'Aug', value: 4.3 }, { period: 'Sep', value: 4.2 },
      { period: 'Oct', value: 4.4 }, { period: 'Nov', value: 4.5 }, { period: 'Dec', value: 4.7 },
    ],
    status: 'healthy',
    confidence: 0.95,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-gross-margin': {
    value: 68.2,
    formattedValue: '68.2%',
    trend: { direction: 'down', percentChange: 2.1, comparisonPeriod: 'vs 2024', positiveIsGood: false },
    sparklineData: [
      { period: 'Jan', value: 70 }, { period: 'Feb', value: 69.5 }, { period: 'Mar', value: 69 },
      { period: 'Apr', value: 68.8 }, { period: 'May', value: 69 }, { period: 'Jun', value: 68.5 },
      { period: 'Jul', value: 68.2 }, { period: 'Aug', value: 68.4 }, { period: 'Sep', value: 68 },
      { period: 'Oct', value: 68.1 }, { period: 'Nov', value: 68.3 }, { period: 'Dec', value: 68.2 },
    ],
    status: 'healthy',
    confidence: 0.92,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-operating-margin': {
    value: 35.0,
    formattedValue: '35.0%',
    trend: { direction: 'up', percentChange: 4.2, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 31 }, { period: 'Q2 24', value: 32 },
      { period: 'Q3 24', value: 33 }, { period: 'Q4 24', value: 35 },
    ],
    status: 'healthy',
    confidence: 0.94,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-net-income': {
    value: 26.2,
    formattedValue: '26.2%',
    trend: { direction: 'up', percentChange: 5.5, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 22 }, { period: 'Q2 24', value: 23 },
      { period: 'Q3 24', value: 24 }, { period: 'Q4 24', value: 26.2 },
    ],
    status: 'healthy',
    confidence: 0.93,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-revenue-waterfall': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: '2024', value: 40.8, type: 'total' },
        { label: 'New Sales', value: 8.2, type: 'increase' },
        { label: 'Expansions', value: 3.5, type: 'increase' },
        { label: 'Churn', value: -2.8, type: 'decrease' },
        { label: 'Downgrades', value: -1.5, type: 'decrease' },
        { label: '2025', value: 48.2, type: 'total' },
      ]
    },
    status: 'healthy',
    confidence: 0.95,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'panel-insights': {
    value: null,
    formattedValue: '',
    insights: [
      { id: '1', type: 'warning', text: 'AR aging up 15% MoM', query: 'Why is accounts receivable aging increasing?' },
      { id: '2', type: 'positive', text: 'OpEx under budget by 8%', query: 'What is driving the OpEx savings?' },
      { id: '3', type: 'warning', text: 'Q1 forecast at risk (-5%)', query: 'What factors are affecting Q1 forecast?' },
      { id: '4', type: 'positive', text: 'Cash position strong', query: 'What is our current cash position and runway?' },
      { id: '5', type: 'improving', text: 'DSO improved 3 days', query: 'How has days sales outstanding changed?' },
    ],
    status: 'healthy',
    confidence: 0.85,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-top-customers': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: 'Acme Corp', value: 4200000 },
        { label: 'TechGiant Inc', value: 3800000 },
        { label: 'Global Solutions', value: 2900000 },
        { label: 'DataFlow Ltd', value: 2100000 },
        { label: 'CloudFirst Co', value: 1800000 },
        { label: 'Nexus Systems', value: 1650000 },
        { label: 'InnovateTech', value: 1420000 },
        { label: 'Quantum Partners', value: 1280000 },
        { label: 'Stellar Labs', value: 1150000 },
        { label: 'Vertex Group', value: 980000 },
      ]
    },
    status: 'healthy',
    confidence: 0.95,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-expenses': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: 'Personnel', value: 15200000, color: '#3B82F6' },
        { label: 'Infrastructure', value: 4800000, color: '#8B5CF6' },
        { label: 'Sales & Marketing', value: 6200000, color: '#EC4899' },
        { label: 'R&D', value: 3500000, color: '#14B8A6' },
        { label: 'G&A', value: 2100000, color: '#F59E0B' },
      ]
    },
    status: 'healthy',
    confidence: 0.92,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-ar-aging': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: 'Q3', segments: [
          { label: 'Current', value: 2800000 },
          { label: '30 days', value: 450000 },
          { label: '60 days', value: 180000 },
          { label: '90+ days', value: 95000 },
        ]},
        { label: 'Q4', segments: [
          { label: 'Current', value: 3200000 },
          { label: '30 days', value: 520000 },
          { label: '60 days', value: 210000 },
          { label: '90+ days', value: 140000 },
        ]},
      ]
    },
    status: 'caution',
    confidence: 0.88,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'nlq-input': {
    value: null,
    formattedValue: '',
    status: 'healthy',
    confidence: 1,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
};

/**
 * Static CRO dashboard data - Revenue Overview
 */
const STATIC_CRO_DATA: Record<string, TileData> = {
  'kpi-bookings': {
    value: 57.5,
    formattedValue: '$57.5M',
    trend: { direction: 'up', percentChange: 22, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 11.2 }, { period: 'Q2 24', value: 11.8 },
      { period: 'Q3 24', value: 12.1 }, { period: 'Q4 24', value: 14.4 },
    ],
    status: 'healthy',
    confidence: 0.95,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-pipeline': {
    value: 145,
    formattedValue: '$145M',
    trend: { direction: 'up', percentChange: 18, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 98 }, { period: 'Q2 24', value: 108 },
      { period: 'Q3 24', value: 125 }, { period: 'Q4 24', value: 145 },
    ],
    status: 'healthy',
    confidence: 0.92,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-win-rate': {
    value: 32,
    formattedValue: '32%',
    trend: { direction: 'up', percentChange: 3.5, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 28 }, { period: 'Q2 24', value: 29 },
      { period: 'Q3 24', value: 30 }, { period: 'Q4 24', value: 32 },
    ],
    status: 'healthy',
    confidence: 0.90,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-nrr': {
    value: 118,
    formattedValue: '118%',
    trend: { direction: 'up', percentChange: 5, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 112 }, { period: 'Q2 24', value: 114 },
      { period: 'Q3 24', value: 116 }, { period: 'Q4 24', value: 118 },
    ],
    status: 'healthy',
    confidence: 0.94,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-pipeline-velocity': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: '2024', value: 47.0, type: 'total' },
        { label: 'New Logo', value: 12.5, type: 'increase' },
        { label: 'Expansion', value: 5.2, type: 'increase' },
        { label: 'Churn', value: -4.8, type: 'decrease' },
        { label: 'Contraction', value: -2.4, type: 'decrease' },
        { label: '2025', value: 57.5, type: 'total' },
      ]
    },
    status: 'healthy',
    confidence: 0.92,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'panel-revenue-insights': {
    value: null,
    formattedValue: '',
    insights: [
      { id: '1', type: 'positive', text: 'Enterprise deals up 35% QoQ', query: 'Show enterprise deal analysis' },
      { id: '2', type: 'warning', text: 'Mid-market churn elevated', query: 'What is causing mid-market churn?' },
      { id: '3', type: 'positive', text: 'NRR at all-time high 118%', query: 'What is driving NRR improvement?' },
      { id: '4', type: 'improving', text: 'Sales cycle down 12 days', query: 'What reduced the sales cycle?' },
      { id: '5', type: 'positive', text: 'Q4 pipeline 2.5x coverage', query: 'Show Q4 pipeline breakdown' },
    ],
    status: 'healthy',
    confidence: 0.88,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-churn-radar': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: 'Enterprise', value: 2.1 },
        { label: 'Mid-Market', value: 8.5 },
        { label: 'SMB', value: 12.3 },
        { label: 'Startup', value: 18.2 },
      ]
    },
    status: 'caution',
    confidence: 0.90,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-win-rate-segment': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: 'Enterprise', value: 42, size: 28.5 },
        { label: 'Mid-Market', value: 35, size: 15.2 },
        { label: 'SMB', value: 28, size: 9.8 },
        { label: 'Startup', value: 22, size: 4.0 },
      ]
    },
    status: 'healthy',
    confidence: 0.91,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-quota-attainment': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: 'Q1', segments: [{ label: 'Attained', value: 92 }, { label: 'Gap', value: 8 }] },
        { label: 'Q2', segments: [{ label: 'Attained', value: 98 }, { label: 'Gap', value: 2 }] },
        { label: 'Q3', segments: [{ label: 'Attained', value: 105 }, { label: 'Gap', value: 0 }] },
        { label: 'Q4', segments: [{ label: 'Attained', value: 96 }, { label: 'Gap', value: 4 }] },
      ]
    },
    status: 'healthy',
    confidence: 0.94,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'nlq-input': {
    value: null,
    formattedValue: '',
    status: 'healthy',
    confidence: 1,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
};

/**
 * Static COO dashboard data - Operations Overview
 */
const STATIC_COO_DATA: Record<string, TileData> = {
  'kpi-headcount': {
    value: 450,
    formattedValue: '450',
    trend: { direction: 'up', percentChange: 12, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 380 }, { period: 'Q2 24', value: 395 },
      { period: 'Q3 24', value: 420 }, { period: 'Q4 24', value: 450 },
    ],
    status: 'healthy',
    confidence: 0.98,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-magic-number': {
    value: 1.2,
    formattedValue: '1.2x',
    trend: { direction: 'up', percentChange: 15, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 0.95 }, { period: 'Q2 24', value: 1.0 },
      { period: 'Q3 24', value: 1.1 }, { period: 'Q4 24', value: 1.2 },
    ],
    status: 'healthy',
    confidence: 0.92,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-ltv-cac': {
    value: 4.2,
    formattedValue: '4.2x',
    trend: { direction: 'up', percentChange: 8, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 3.6 }, { period: 'Q2 24', value: 3.8 },
      { period: 'Q3 24', value: 4.0 }, { period: 'Q4 24', value: 4.2 },
    ],
    status: 'healthy',
    confidence: 0.90,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-nps': {
    value: 52,
    formattedValue: '52',
    trend: { direction: 'up', percentChange: 6, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 45 }, { period: 'Q2 24', value: 47 },
      { period: 'Q3 24', value: 50 }, { period: 'Q4 24', value: 52 },
    ],
    status: 'healthy',
    confidence: 0.88,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-headcount-by-function': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: 'Engineering', value: 150 },
        { label: 'Sales', value: 85 },
        { label: 'Customer Success', value: 65 },
        { label: 'Marketing', value: 45 },
        { label: 'Product', value: 40 },
        { label: 'G&A', value: 35 },
        { label: 'Finance', value: 30 },
      ]
    },
    status: 'healthy',
    confidence: 0.98,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'panel-operational-insights': {
    value: null,
    formattedValue: '',
    insights: [
      { id: '1', type: 'positive', text: 'Magic Number at 1.2x (healthy)', query: 'What improved our magic number?' },
      { id: '2', type: 'improving', text: 'Hiring on track: 94% of plan', query: 'Show hiring progress by department' },
      { id: '3', type: 'positive', text: 'LTV/CAC at 4.2x', query: 'What is driving LTV improvement?' },
      { id: '4', type: 'warning', text: 'Support ticket volume up 18%', query: 'What is causing increased tickets?' },
      { id: '5', type: 'positive', text: 'NPS improved 6 points YoY', query: 'What drove the NPS improvement?' },
    ],
    status: 'healthy',
    confidence: 0.85,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-utilization-rates': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: 'Professional Services', value: 82 },
        { label: 'Support', value: 78 },
        { label: 'Engineering', value: 85 },
        { label: 'Customer Success', value: 88 },
      ]
    },
    status: 'healthy',
    confidence: 0.90,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-service-metrics': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { period: 'Q1', implementation: 45, timeToValue: 32 },
        { period: 'Q2', implementation: 42, timeToValue: 28 },
        { period: 'Q3', implementation: 38, timeToValue: 25 },
        { period: 'Q4', implementation: 35, timeToValue: 22 },
      ]
    },
    status: 'healthy',
    confidence: 0.88,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-csat-trend': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { period: 'Jan', value: 4.2 },
        { period: 'Feb', value: 4.3 },
        { period: 'Mar', value: 4.2 },
        { period: 'Apr', value: 4.4 },
        { period: 'May', value: 4.3 },
        { period: 'Jun', value: 4.5 },
        { period: 'Jul', value: 4.4 },
        { period: 'Aug', value: 4.5 },
        { period: 'Sep', value: 4.6 },
        { period: 'Oct', value: 4.5 },
        { period: 'Nov', value: 4.6 },
        { period: 'Dec', value: 4.7 },
      ]
    },
    status: 'healthy',
    confidence: 0.92,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'nlq-input': {
    value: null,
    formattedValue: '',
    status: 'healthy',
    confidence: 1,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
};

/**
 * Static CTO dashboard data - Technology Overview
 */
const STATIC_CTO_DATA: Record<string, TileData> = {
  'kpi-uptime': {
    value: 99.95,
    formattedValue: '99.95%',
    trend: { direction: 'up', percentChange: 0.02, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 99.90 }, { period: 'Q2 24', value: 99.92 },
      { period: 'Q3 24', value: 99.94 }, { period: 'Q4 24', value: 99.95 },
    ],
    status: 'healthy',
    confidence: 0.99,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-velocity': {
    value: 65,
    formattedValue: '65 pts',
    trend: { direction: 'up', percentChange: 12, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 52 }, { period: 'Q2 24', value: 56 },
      { period: 'Q3 24', value: 60 }, { period: 'Q4 24', value: 65 },
    ],
    status: 'healthy',
    confidence: 0.92,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-deploys-week': {
    value: 45,
    formattedValue: '45/wk',
    trend: { direction: 'up', percentChange: 28, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 28 }, { period: 'Q2 24', value: 32 },
      { period: 'Q3 24', value: 38 }, { period: 'Q4 24', value: 45 },
    ],
    status: 'healthy',
    confidence: 0.95,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-tech-debt': {
    value: 15,
    formattedValue: '15%',
    trend: { direction: 'down', percentChange: 8, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 22 }, { period: 'Q2 24', value: 20 },
      { period: 'Q3 24', value: 18 }, { period: 'Q4 24', value: 15 },
    ],
    status: 'healthy',
    confidence: 0.88,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-platform-incidents': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { period: 'Jan', p1: 0, p2: 2 },
        { period: 'Feb', p1: 1, p2: 1 },
        { period: 'Mar', p1: 0, p2: 2 },
        { period: 'Apr', p1: 0, p2: 1 },
        { period: 'May', p1: 0, p2: 2 },
        { period: 'Jun', p1: 1, p2: 1 },
        { period: 'Jul', p1: 0, p2: 1 },
        { period: 'Aug', p1: 0, p2: 2 },
        { period: 'Sep', p1: 0, p2: 1 },
        { period: 'Oct', p1: 0, p2: 1 },
        { period: 'Nov', p1: 0, p2: 0 },
        { period: 'Dec', p1: 0, p2: 1 },
      ]
    },
    status: 'healthy',
    confidence: 0.98,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'panel-tech-insights': {
    value: null,
    formattedValue: '',
    insights: [
      { id: '1', type: 'positive', text: 'Zero P1 incidents in Q4', query: 'What prevented P1 incidents?' },
      { id: '2', type: 'improving', text: 'Deploy frequency up 28% YoY', query: 'What improved deployment velocity?' },
      { id: '3', type: 'positive', text: 'Tech debt reduced to 15%', query: 'How was tech debt reduced?' },
      { id: '4', type: 'improving', text: 'Test coverage now at 82%', query: 'Show test coverage by module' },
      { id: '5', type: 'positive', text: 'MTTR down to 18 minutes', query: 'What improved incident response?' },
    ],
    status: 'healthy',
    confidence: 0.90,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-code-quality': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: 'Test Coverage', value: 82 },
        { label: 'Code Review', value: 95 },
        { label: 'Lint Pass', value: 98 },
        { label: 'Build Success', value: 96 },
      ]
    },
    status: 'healthy',
    confidence: 0.94,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-deployment-metrics': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { period: 'Jan', value: 94 },
        { period: 'Feb', value: 95 },
        { period: 'Mar', value: 93 },
        { period: 'Apr', value: 96 },
        { period: 'May', value: 97 },
        { period: 'Jun', value: 95 },
        { period: 'Jul', value: 98 },
        { period: 'Aug', value: 97 },
        { period: 'Sep', value: 98 },
        { period: 'Oct', value: 99 },
        { period: 'Nov', value: 98 },
        { period: 'Dec', value: 99 },
      ]
    },
    status: 'healthy',
    confidence: 0.96,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-cloud-cost': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: 'Compute', value: 42000 },
        { label: 'Storage', value: 18000 },
        { label: 'Network', value: 12000 },
        { label: 'Database', value: 15000 },
        { label: 'Other', value: 8000 },
      ]
    },
    status: 'healthy',
    confidence: 0.95,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'nlq-input': {
    value: null,
    formattedValue: '',
    status: 'healthy',
    confidence: 1,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
};

/**
 * API response structure from /api/v1/query endpoint
 */
interface NLQApiResponse {
  success: boolean;
  answer?: string;
  value?: number | string;
  unit?: string;
  confidence: number;
  parsed_intent?: string;
  resolved_metric?: string;
  resolved_period?: string;
  error_code?: string;
  error_message?: string;
  trend?: {
    direction: 'up' | 'down' | 'flat';
    value: number;
    is_positive: boolean;
    comparison_period?: string;
  };
  sparkline_data?: Array<{ period: string; value: number }>;
  insights?: Array<{
    id: string;
    type: 'warning' | 'positive' | 'declining' | 'improving';
    text: string;
    query: string;
  }>;
}

/**
 * Fetch data for a single tile via the NLQ API
 */
async function fetchTileData(
  tile: TileConfig,
  timeRange: string
): Promise<TileData> {
  // Determine the query based on tile type
  let query = '';
  if (isKPITile(tile)) {
    query = tile.kpi.primaryQuery;
  } else if (isChartTile(tile)) {
    query = tile.chart.query;
  } else if (isInsightsTile(tile)) {
    query = tile.insights.query;
  }

  if (!query) {
    return createEmptyTileData();
  }

  // Append time range to query if not already included
  const timeRangeMap: Record<string, string> = {
    MTD: 'month to date',
    QTD: 'quarter to date',
    YTD: 'year to date',
    L12M: 'last 12 months',
  };

  const timeRangeText = timeRangeMap[timeRange] || timeRange;
  const fullQuery = query.toLowerCase().includes(timeRange.toLowerCase())
    ? query
    : `${query} ${timeRangeText}`;

  try {
    const response = await fetch('/api/v1/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: fullQuery,
        reference_date: new Date().toISOString().split('T')[0],
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data: NLQApiResponse = await response.json();

    if (!data.success) {
      return {
        value: null,
        formattedValue: 'Error',
        status: 'critical',
        confidence: 0,
        loading: false,
        error: data.error_message || 'Query failed',
        lastUpdated: new Date(),
      };
    }

    // Transform API response to TileData
    return transformApiResponseToTileData(data, tile);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    return {
      value: null,
      formattedValue: 'Error',
      status: 'critical',
      confidence: 0,
      loading: false,
      error: errorMessage,
      lastUpdated: new Date(),
    };
  }
}

/**
 * Transform the NLQ API response into TileData format
 */
function transformApiResponseToTileData(
  response: NLQApiResponse,
  tile: TileConfig
): TileData {
  // Build trend data if available
  let trend: TrendData | undefined;
  if (response.trend) {
    trend = {
      direction: response.trend.direction,
      percentChange: response.trend.value,
      comparisonPeriod: response.trend.comparison_period || 'vs prior period',
      positiveIsGood: response.trend.is_positive,
    };
  }

  // Build sparkline data if available
  let sparklineData: SparklineDataPoint[] | undefined;
  if (response.sparkline_data && response.sparkline_data.length > 0) {
    sparklineData = response.sparkline_data.map((point) => ({
      period: point.period,
      value: point.value,
    }));
  }

  // Determine status based on confidence and trend
  let status: StatusType = 'healthy';
  if (response.confidence < 0.5) {
    status = 'critical';
  } else if (response.confidence < 0.8) {
    status = 'caution';
  }

  // Format the value based on tile type
  let formattedValue = '';
  if (response.answer) {
    formattedValue = response.answer;
  } else if (response.value !== undefined) {
    formattedValue = formatValue(response.value, response.unit, tile);
  }

  // Build insights array if this is an insights tile
  let insights: InsightItem[] | undefined;
  if (isInsightsTile(tile) && response.insights) {
    insights = response.insights;
  }

  return {
    value: response.value ?? null,
    formattedValue,
    trend,
    sparklineData,
    status,
    confidence: response.confidence,
    loading: false,
    error: null,
    lastUpdated: new Date(),
    rawData: response,
    insights,
  };
}

/**
 * Format a numeric value based on unit and tile configuration
 */
function formatValue(
  value: number | string,
  unit: string | undefined,
  tile: TileConfig
): string {
  if (typeof value === 'string') {
    return value;
  }

  // Determine format from tile config
  let format = 'number';
  if (isKPITile(tile)) {
    format = tile.kpi.format;
  }

  switch (format) {
    case 'currency':
      if (Math.abs(value) >= 1_000_000_000) {
        return `$${(value / 1_000_000_000).toFixed(1)}B`;
      } else if (Math.abs(value) >= 1_000_000) {
        return `$${(value / 1_000_000).toFixed(1)}M`;
      } else if (Math.abs(value) >= 1_000) {
        return `$${(value / 1_000).toFixed(0)}K`;
      }
      return `$${value.toFixed(0)}`;

    case 'percent':
      return `${value.toFixed(1)}%`;

    case 'months':
      return `${Math.round(value)} month${Math.round(value) !== 1 ? 's' : ''}`;

    default:
      if (unit === '%') {
        return `${value.toFixed(1)}%`;
      }
      if (unit === '$' || unit === 'currency') {
        return formatValue(value, undefined, { ...tile, kpi: { ...tile.kpi!, format: 'currency' } } as TileConfig);
      }
      if (Math.abs(value) >= 1_000_000) {
        return `${(value / 1_000_000).toFixed(1)}M`;
      } else if (Math.abs(value) >= 1_000) {
        return `${(value / 1_000).toFixed(1)}K`;
      }
      return value.toLocaleString();
  }
}

/**
 * Create an empty tile data object for loading/initial state
 */
function createEmptyTileData(loading = false): TileData {
  return {
    value: null,
    formattedValue: '',
    status: 'healthy',
    confidence: 0,
    loading,
    error: null,
    lastUpdated: null,
  };
}

/**
 * Return type for the useDashboardData hook
 */
export interface UseDashboardDataReturn {
  /** Data for all tiles keyed by tile ID */
  data: Record<string, TileData>;
  /** Whether any tiles are currently loading */
  loading: boolean;
  /** Global error message if all fetches failed */
  error: string | null;
  /** Refresh all tile data */
  refresh: () => Promise<void>;
  /** Refresh data for a specific tile */
  refreshTile: (tileId: string) => Promise<void>;
  /** Last refresh timestamp */
  lastRefreshed: Date | null;
}

/**
 * Hook to fetch and manage dashboard tile data
 *
 * @param config - Dashboard configuration containing tile definitions
 * @param timeRange - Selected time range for data filtering
 * @returns Object containing data, loading state, and refresh functions
 */
export const useDashboardData = (
  config: DashboardConfig | null,
  timeRange: string
): UseDashboardDataReturn => {
  const [data, setData] = useState<Record<string, TileData>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  // Track the refresh interval
  const refreshIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isInitialFetch = useRef(true);

  /**
   * Load data for all visible tiles - uses static data for instant load
   */
  const fetchAllTileData = useCallback(async () => {
    if (!config || !config.tiles || config.tiles.length === 0) {
      return;
    }

    // Use static data for all persona dashboards - instant load!
    // This avoids 10+ slow API calls per dashboard
    const staticDataMap: Record<string, Record<string, TileData>> = {
      'cfo-dashboard-v1': STATIC_CFO_DATA,
      'cro-dashboard-v1': STATIC_CRO_DATA,
      'coo-dashboard-v1': STATIC_COO_DATA,
      'cto-dashboard-v1': STATIC_CTO_DATA,
    };

    if (config.id in staticDataMap) {
      setData(staticDataMap[config.id]);
      setLastRefreshed(new Date());
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    // Initialize all tiles with loading state
    const initialData: Record<string, TileData> = {};
    config.tiles
      .filter((tile) => tile.visible !== false)
      .forEach((tile) => {
        initialData[tile.id] = createEmptyTileData(true);
      });
    setData(initialData);

    // Fetch data for all tiles in parallel
    const visibleTiles = config.tiles.filter((tile) => tile.visible !== false);
    const fetchPromises = visibleTiles.map(async (tile) => {
      const tileData = await fetchTileData(tile, timeRange);
      return { tileId: tile.id, data: tileData };
    });

    try {
      const results = await Promise.allSettled(fetchPromises);

      const newData: Record<string, TileData> = {};
      let allFailed = true;
      let lastError: string | null = null;

      results.forEach((result, index) => {
        const tileId = visibleTiles[index].id;
        if (result.status === 'fulfilled') {
          newData[tileId] = result.value.data;
          if (!result.value.data.error) {
            allFailed = false;
          } else {
            lastError = result.value.data.error;
          }
        } else {
          newData[tileId] = {
            ...createEmptyTileData(),
            error: result.reason?.message || 'Fetch failed',
          };
          lastError = result.reason?.message || 'Fetch failed';
        }
      });

      setData(newData);
      setLastRefreshed(new Date());

      if (allFailed && lastError) {
        setError(lastError);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
    } finally {
      setLoading(false);
      isInitialFetch.current = false;
    }
  }, [config, timeRange]);

  /**
   * Refresh data for a specific tile
   */
  const refreshTile = useCallback(
    async (tileId: string) => {
      if (!config) return;

      const tile = config.tiles.find((t) => t.id === tileId);
      if (!tile) return;

      // Set loading state for this tile
      setData((prev) => ({
        ...prev,
        [tileId]: { ...prev[tileId], loading: true },
      }));

      const tileData = await fetchTileData(tile, timeRange);

      setData((prev) => ({
        ...prev,
        [tileId]: tileData,
      }));
    },
    [config, timeRange]
  );

  /**
   * Refresh function exposed to consumers
   */
  const refresh = useCallback(async () => {
    await fetchAllTileData();
  }, [fetchAllTileData]);

  // Fetch data on mount and when config/timeRange changes
  useEffect(() => {
    fetchAllTileData();
  }, [fetchAllTileData]);

  // Set up auto-refresh interval
  useEffect(() => {
    // Clear any existing interval
    if (refreshIntervalRef.current) {
      clearInterval(refreshIntervalRef.current);
      refreshIntervalRef.current = null;
    }

    // Set up new interval if configured
    if (config && config.refreshInterval > 0) {
      refreshIntervalRef.current = setInterval(() => {
        fetchAllTileData();
      }, config.refreshInterval * 1000); // Convert seconds to milliseconds
    }

    // Cleanup on unmount
    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }
    };
  }, [config?.refreshInterval, fetchAllTileData]);

  return {
    data,
    loading,
    error,
    refresh,
    refreshTile,
    lastRefreshed,
  };
};

export default useDashboardData;
