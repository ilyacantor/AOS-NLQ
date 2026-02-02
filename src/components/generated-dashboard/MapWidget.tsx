/**
 * MapWidget - Geographic revenue visualization with actual world map
 *
 * Shows revenue distribution on a proper world map (AMER, EMEA, APAC, LATAM)
 */

import { useMemo } from 'react';
import { Widget, WidgetData } from '../../types/generated-dashboard';

interface MapWidgetProps {
  widget: Widget;
  data: WidgetData;
  height: number;
  onClick?: (value?: string) => void;
}

// Simplified but recognizable continent paths (viewBox 0 0 1000 500)
const REGION_PATHS: Record<string, { paths: string[]; labelX: number; labelY: number }> = {
  AMER: {
    // North America + South America
    paths: [
      // North America
      'M 80,60 L 120,50 L 180,55 L 220,80 L 230,120 L 210,150 L 180,170 L 140,180 L 100,175 L 70,150 L 60,110 L 65,80 Z',
      // Central America
      'M 140,180 L 160,190 L 170,220 L 155,240 L 140,235 L 130,210 L 135,190 Z',
      // South America
      'M 155,240 L 180,250 L 210,280 L 220,340 L 200,400 L 160,420 L 130,390 L 120,330 L 130,280 L 145,250 Z',
    ],
    labelX: 150,
    labelY: 140,
  },
  EMEA: {
    // Europe + Middle East + Africa
    paths: [
      // Europe
      'M 420,60 L 480,50 L 540,55 L 560,80 L 550,110 L 520,130 L 480,135 L 440,130 L 410,110 L 405,80 Z',
      // Middle East
      'M 540,130 L 580,125 L 620,140 L 610,180 L 570,190 L 540,175 L 530,150 Z',
      // Africa
      'M 420,150 L 480,145 L 540,160 L 560,200 L 550,280 L 520,350 L 470,380 L 420,360 L 400,300 L 390,230 L 400,180 Z',
    ],
    labelX: 480,
    labelY: 200,
  },
  APAC: {
    // Asia + Australia/Pacific
    paths: [
      // Asia (Russia + East Asia)
      'M 560,40 L 700,35 L 820,50 L 880,80 L 900,130 L 880,180 L 820,200 L 740,195 L 680,180 L 620,150 L 580,120 L 560,80 Z',
      // South/Southeast Asia
      'M 680,180 L 750,200 L 800,230 L 820,280 L 780,300 L 720,290 L 680,260 L 660,220 Z',
      // Australia
      'M 780,340 L 860,330 L 920,360 L 930,410 L 890,450 L 820,460 L 770,430 L 760,380 Z',
    ],
    labelX: 780,
    labelY: 150,
  },
  LATAM: {
    // Latin America (shown as part of AMER but can be highlighted separately)
    paths: [
      'M 140,200 L 175,210 L 200,250 L 215,320 L 195,390 L 155,410 L 125,380 L 115,320 L 125,260 L 135,220 Z',
    ],
    labelX: 160,
    labelY: 310,
  },
};

// Get color with opacity based on percentage
function getRegionFill(percentage: number): string {
  if (percentage <= 0) return '#1e293b';
  // Cyan gradient based on percentage
  const opacity = 0.3 + (percentage / 100) * 0.7;
  return `rgba(11, 202, 217, ${opacity})`;
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
      const regionKey = r.region?.toUpperCase() || '';
      lookup[regionKey] = {
        value: r.value || 0,
        percentage: r.percentage || 0,
      };
    });
    return lookup;
  }, [regionData]);

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-slate-400">{widget.title}</h3>
        <div className="text-right">
          <span className="text-lg font-bold text-white">{formatValue(total)}</span>
          <span className="text-xs text-slate-500 ml-1">total</span>
        </div>
      </div>

      <div className="flex-1 relative" style={{ minHeight: Math.max(height - 100, 150) }}>
        {/* SVG World Map */}
        <svg
          viewBox="0 0 1000 500"
          className="w-full h-full"
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Ocean background */}
          <rect width="1000" height="500" fill="#0a1628" />

          {/* Grid lines for visual effect */}
          <g stroke="#1e293b" strokeWidth="0.5" opacity="0.3">
            {[100, 200, 300, 400].map(y => (
              <line key={`h-${y}`} x1="0" y1={y} x2="1000" y2={y} />
            ))}
            {[200, 400, 600, 800].map(x => (
              <line key={`v-${x}`} x1={x} y1="0" x2={x} y2="500" />
            ))}
          </g>

          {/* Render each region */}
          {Object.entries(REGION_PATHS).map(([regionKey, config]) => {
            const regionInfo = regionLookup[regionKey] || { value: 0, percentage: 0 };
            const hasData = regionInfo.value > 0;
            const fillColor = getRegionFill(regionInfo.percentage);

            return (
              <g
                key={regionKey}
                onClick={() => hasDrillDown && onClick?.(regionKey)}
                style={{ cursor: hasDrillDown ? 'pointer' : 'default' }}
                className="transition-all duration-200 hover:opacity-80"
              >
                {/* Region landmass shapes */}
                {config.paths.map((path, i) => (
                  <path
                    key={`${regionKey}-${i}`}
                    d={path}
                    fill={fillColor}
                    stroke={hasData ? '#0BCAD9' : '#334155'}
                    strokeWidth={hasData ? 1.5 : 0.5}
                  />
                ))}

                {/* Region label and value */}
                {hasData && (
                  <g>
                    {/* Background for text readability */}
                    <rect
                      x={config.labelX - 40}
                      y={config.labelY - 12}
                      width="80"
                      height="36"
                      fill="rgba(15, 23, 42, 0.8)"
                      rx="4"
                    />
                    <text
                      x={config.labelX}
                      y={config.labelY}
                      textAnchor="middle"
                      fill="#94a3b8"
                      fontSize="11"
                      fontWeight="500"
                    >
                      {regionKey}
                    </text>
                    <text
                      x={config.labelX}
                      y={config.labelY + 14}
                      textAnchor="middle"
                      fill="#ffffff"
                      fontSize="12"
                      fontWeight="bold"
                    >
                      {regionInfo.percentage.toFixed(0)}%
                    </text>
                  </g>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend */}
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
                style={{ backgroundColor: getRegionFill(r.percentage || 0) }}
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
