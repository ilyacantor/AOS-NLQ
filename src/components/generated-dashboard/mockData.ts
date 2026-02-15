/**
 * Mock data generators for dashboard widgets (MVP fallback).
 *
 * Used when the backend does not return widget_data for a widget,
 * so the UI can still display representative visualizations.
 */

import { Widget, WidgetData } from '../../types/generated-dashboard';

export async function generateMockWidgetData(widget: Widget): Promise<WidgetData> {
  await new Promise(resolve => setTimeout(resolve, 300 + Math.random() * 200));

  const metric = widget.data.metrics[0]?.metric || 'revenue';

  switch (widget.type) {
    case 'kpi_card':
      return generateKPIData(metric);
    case 'line_chart':
    case 'area_chart':
      return generateTimeSeriesData(metric, widget.data.time?.granularity || 'quarterly');
    case 'bar_chart':
    case 'horizontal_bar':
      return generateCategoryData(metric, widget.data.dimensions[0]?.dimension);
    case 'stacked_bar':
      return generateStackedData(widget.data.metrics, widget.data.dimensions[0]?.dimension);
    case 'donut_chart':
      return generateDonutData(metric, widget.data.dimensions[0]?.dimension);
    case 'data_table':
      return generateTableData(widget.data.metrics, widget.data.dimensions);
    default:
      return { loading: false };
  }
}

function generateKPIData(metric: string): WidgetData {
  const values: Record<string, { value: number; format: string; trend: number }> = {
    revenue: { value: 200, format: '$200M', trend: 15.2 },
    gross_margin_pct: { value: 65, format: '65.0%', trend: 2.3 },
    net_income: { value: 45, format: '$45M', trend: 18.5 },
    pipeline: { value: 575, format: '$575M', trend: 8.7 },
    churn: { value: 2.5, format: '2.5%', trend: -0.3 },
    nrr: { value: 118, format: '118%', trend: 3.0 },
    headcount: { value: 450, format: '450', trend: 12.5 },
    win_rate: { value: 32, format: '32%', trend: 4.2 },
    quota_attainment: { value: 95.8, format: '95.8%', trend: 5.1 },
    magic_number: { value: 0.9, format: '0.9x', trend: 0.1 },
    ltv_cac: { value: 4.2, format: '4.2x', trend: 0.3 },
    uptime_pct: { value: 99.95, format: '99.95%', trend: 0.02 },
    p1_incidents: { value: 3, format: '3', trend: -2 },
  };

  const data = values[metric] || { value: 100, format: '100', trend: 5.0 };
  const isPositive = data.trend > 0;

  return {
    loading: false,
    value: data.value,
    formatted_value: data.format,
    trend: {
      direction: isPositive ? 'up' : data.trend < 0 ? 'down' : 'flat',
      percent_change: Math.abs(data.trend),
      comparison_label: 'vs prior period',
    },
    sparkline_data: Array.from({ length: 8 }, () => data.value * (0.8 + Math.random() * 0.4)),
  };
}

function generateTimeSeriesData(metric: string, granularity: string): WidgetData {
  const periods = granularity === 'quarterly'
    ? ['Q1 2024', 'Q2 2024', 'Q3 2024', 'Q4 2024', 'Q1 2025', 'Q2 2025', 'Q3 2025', 'Q4 2025']
    : ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  const baseValue = metric === 'revenue' ? 40 : metric.includes('pct') ? 60 : 100;
  const growth = 1.05;

  return {
    loading: false,
    categories: periods,
    series: [{
      name: metric,
      data: periods.map((label, i) => ({
        label,
        value: Math.round(baseValue * Math.pow(growth, i) * (0.9 + Math.random() * 0.2) * 10) / 10,
      })),
    }],
  };
}

function generateCategoryData(metric: string, dimension?: string): WidgetData {
  const categories = dimension === 'rep'
    ? ['John Smith', 'Sarah Jones', 'Mike Chen', 'Lisa Wang', 'Tom Brown']
    : dimension === 'product'
    ? ['Enterprise', 'Professional', 'Team', 'Starter']
    : ['AMER', 'EMEA', 'APAC', 'LATAM'];

  const baseValue = metric === 'revenue' ? 50 : 20;

  return {
    loading: false,
    categories,
    series: [{
      name: metric,
      data: categories.map((label, i) => ({
        label,
        value: Math.round(baseValue * (1 - i * 0.15) * (0.8 + Math.random() * 0.4) * 10) / 10,
      })),
    }],
  };
}

function generateStackedData(metrics: Array<{ metric: string }>, _dimension?: string): WidgetData {
  const categories = ['Q1', 'Q2', 'Q3', 'Q4'];

  return {
    loading: false,
    categories,
    series: metrics.slice(0, 3).map((m, mi) => ({
      name: m.metric,
      data: categories.map((label, i) => ({
        label,
        value: Math.round((30 - mi * 5) * (1 + i * 0.1) * (0.8 + Math.random() * 0.4) * 10) / 10,
      })),
    })),
  };
}

function generateDonutData(metric: string, dimension?: string): WidgetData {
  const categories = dimension === 'product'
    ? ['Enterprise', 'Professional', 'Team', 'Starter']
    : ['AMER', 'EMEA', 'APAC', 'LATAM'];

  return {
    loading: false,
    categories,
    series: [{
      name: metric,
      data: categories.map((label, i) => ({
        label,
        value: Math.round((40 - i * 8) * (0.8 + Math.random() * 0.4)),
      })),
    }],
  };
}

function generateTableData(
  metrics: Array<{ metric: string }>,
  dimensions: Array<{ dimension: string }>
): WidgetData {
  const dimension = dimensions[0]?.dimension || 'region';
  const categories = dimension === 'rep'
    ? ['John Smith', 'Sarah Jones', 'Mike Chen', 'Lisa Wang', 'Tom Brown']
    : ['AMER', 'EMEA', 'APAC', 'LATAM'];

  return {
    loading: false,
    rows: categories.map(cat => {
      const row: Record<string, any> = { [dimension]: cat };
      metrics.forEach(m => {
        const baseValue = m.metric === 'revenue' ? 50 : 20;
        row[m.metric] = Math.round(baseValue * (0.8 + Math.random() * 0.4) * 10) / 10;
      });
      return row;
    }),
  };
}
