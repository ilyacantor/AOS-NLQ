/**
 * MapWidget - Geographic revenue visualization
 *
 * Shows revenue distribution on an interactive world map (AMER, EMEA, APAC, LATAM)
 * Responds to prompts like "show me where revenue comes from"
 */

import { useMemo } from 'react';
import { Widget, WidgetData } from '../../types/generated-dashboard';

interface MapWidgetProps {
  widget: Widget;
  data: WidgetData;
  height: number;
  onClick?: (value?: string) => void;
}

// Region configurations with SVG paths for simplified world regions
const REGION_CONFIGS: Record<string, {
  path: string;
  label: string;
  labelX: number;
  labelY: number;
  countries: string[];
}> = {
  AMER: {
    path: 'M 50,50 L 120,40 L 140,80 L 130,150 L 100,200 L 60,180 L 40,120 L 30,80 Z',
    label: 'Americas',
    labelX: 85,
    labelY: 120,
    countries: ['USA', 'Canada', 'Brazil', 'Mexico'],
  },
  EMEA: {
    path: 'M 180,30 L 280,25 L 300,60 L 290,120 L 250,160 L 200,150 L 170,100 L 160,60 Z',
    label: 'EMEA',
    labelX: 230,
    labelY: 90,
    countries: ['UK', 'Germany', 'France', 'UAE'],
  },
  APAC: {
    path: 'M 300,50 L 380,40 L 400,100 L 390,160 L 340,180 L 300,150 L 290,100 Z',
    label: 'Asia Pacific',
    labelX: 345,
    labelY: 110,
    countries: ['Japan', 'Australia', 'Singapore', 'India'],
  },
  LATAM: {
    path: 'M 80,180 L 110,170 L 130,200 L 120,260 L 90,280 L 60,250 L 55,210 Z',
    label: 'Latin America',
    labelX: 95,
    labelY: 225,
    countries: ['Brazil', 'Mexico', 'Argentina', 'Chile'],
  },
};

// Get color intensity based on percentage (higher = more saturated)
function getRegionColor(percentage: number, baseColor: string = '#3B82F6'): string {
  // Convert percentage (0-100) to opacity (0.2-1.0)
  const minOpacity = 0.2;
  const maxOpacity = 1.0;
  const opacity = minOpacity + (percentage / 100) * (maxOpacity - minOpacity);

  // Parse the base color and apply opacity
  const r = parseInt(baseColor.slice(1, 3), 16);
  const g = parseInt(baseColor.slice(3, 5), 16);
  const b = parseInt(baseColor.slice(5, 7), 16);

  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

// Format currency values
function formatValue(value: number): string {
  if (value >= 1000000) {
    return `$${(value / 1000000).toFixed(1)}M`;
  } else if (value >= 1000) {
    return `$${(value / 1000).toFixed(0)}K`;
  }
  return `$${value.toFixed(0)}`;
}

export function MapWidget({ widget, data, height, onClick }: MapWidgetProps) {
  // Extract region data from widget data
  const regionData = useMemo(() => {
    if (data.map_data?.regions) {
      return data.map_data.regions;
    }

    // Fallback: try to extract from series data
    if (data.series?.[0]?.data) {
      const seriesData = data.series[0].data;
      const total = seriesData.reduce((sum, d) => sum + (d.value || 0), 0);
      return seriesData.map(d => ({
        region: d.label || '',
        value: d.value || 0,
        percentage: total > 0 ? ((d.value || 0) / total) * 100 : 0,
      }));
    }

    return [];
  }, [data]);

  const total = useMemo(() => {
    if (data.map_data?.total) return data.map_data.total;
    return regionData.reduce((sum, r) => sum + (r.value || 0), 0);
  }, [data, regionData]);

  const hasDrillDown = widget.interactions?.some(i => i.type === 'drill_down' && i.enabled);

  // Create a lookup for region data
  const regionLookup = useMemo(() => {
    const lookup: Record<string, { value: number; percentage: number }> = {};
    regionData.forEach(r => {
      lookup[r.region?.toUpperCase() || ''] = {
        value: r.value || 0,
        percentage: r.percentage || 0,
      };
    });
    return lookup;
  }, [regionData]);

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-slate-400">{widget.title}</h3>
        <div className="text-right">
          <span className="text-lg font-bold text-white">{formatValue(total)}</span>
          <span className="text-xs text-slate-500 ml-1">Total</span>
        </div>
      </div>

      <div className="flex-1 relative" style={{ minHeight: height - 100 }}>
        {/* SVG Map */}
        <svg
          viewBox="0 0 450 300"
          className="w-full h-full"
          style={{ maxHeight: height - 120 }}
        >
          {/* Background */}
          <rect width="450" height="300" fill="#0f172a" rx="8" />

          {/* Grid lines for visual effect */}
          <g stroke="#1e293b" strokeWidth="0.5" opacity="0.5">
            {[50, 100, 150, 200, 250].map(y => (
              <line key={`h-${y}`} x1="0" y1={y} x2="450" y2={y} />
            ))}
            {[100, 200, 300, 400].map(x => (
              <line key={`v-${x}`} x1={x} y1="0" x2={x} y2="300" />
            ))}
          </g>

          {/* Regions */}
          {Object.entries(REGION_CONFIGS).map(([regionKey, config]) => {
            const regionInfo = regionLookup[regionKey] || { value: 0, percentage: 0 };
            const hasData = regionInfo.value > 0;

            return (
              <g
                key={regionKey}
                onClick={() => hasDrillDown && onClick?.(regionKey)}
                style={{ cursor: hasDrillDown ? 'pointer' : 'default' }}
                className="transition-opacity hover:opacity-80"
              >
                {/* Region shape */}
                <path
                  d={config.path}
                  fill={hasData ? getRegionColor(regionInfo.percentage, '#0BCAD9') : '#1e293b'}
                  stroke="#334155"
                  strokeWidth="1"
                />

                {/* Region label */}
                <text
                  x={config.labelX}
                  y={config.labelY - 12}
                  textAnchor="middle"
                  fill="#94a3b8"
                  fontSize="10"
                  fontWeight="500"
                >
                  {config.label}
                </text>

                {/* Value */}
                {hasData && (
                  <>
                    <text
                      x={config.labelX}
                      y={config.labelY + 4}
                      textAnchor="middle"
                      fill="#ffffff"
                      fontSize="12"
                      fontWeight="bold"
                    >
                      {formatValue(regionInfo.value)}
                    </text>
                    <text
                      x={config.labelX}
                      y={config.labelY + 18}
                      textAnchor="middle"
                      fill="#64748b"
                      fontSize="9"
                    >
                      {regionInfo.percentage.toFixed(1)}%
                    </text>
                  </>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend / Region breakdown */}
      <div className="flex flex-wrap gap-3 mt-2 justify-center">
        {regionData
          .filter(r => r.value > 0)
          .sort((a, b) => (b.value || 0) - (a.value || 0))
          .map(r => (
            <div
              key={r.region}
              className={`flex items-center gap-2 px-2 py-1 rounded ${
                hasDrillDown ? 'cursor-pointer hover:bg-slate-800' : ''
              }`}
              onClick={() => hasDrillDown && onClick?.(r.region)}
            >
              <div
                className="w-3 h-3 rounded-sm"
                style={{ backgroundColor: getRegionColor(r.percentage || 0, '#0BCAD9') }}
              />
              <span className="text-xs text-slate-400">{r.region}</span>
              <span className="text-xs font-medium text-slate-300">
                {(r.percentage || 0).toFixed(0)}%
              </span>
            </div>
          ))}
      </div>
    </div>
  );
}

export default MapWidget;
