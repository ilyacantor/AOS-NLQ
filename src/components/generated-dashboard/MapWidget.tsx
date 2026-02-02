/**
 * MapWidget - Geographic revenue visualization with world map
 * Pure SVG implementation - no external dependencies
 */

import { useState, useMemo } from 'react';
import { Widget, WidgetData } from '../../types/generated-dashboard';

interface MapWidgetProps {
  widget: Widget;
  data: WidgetData;
  height: number;
  onClick?: (value?: string) => void;
}

interface RegionData {
  region: string;
  value: number;
  percentage?: number;
}

// Simplified continent paths (viewBox 0 0 960 480)
const REGION_PATHS: Record<string, { paths: string[]; center: [number, number] }> = {
  AMER: {
    center: [180, 200],
    paths: [
      // North America
      `M 80,60 L 120,45 L 180,50 L 240,70 L 280,100 L 270,140 L 240,170 
       L 200,190 L 160,195 L 120,185 L 90,160 L 70,120 L 75,85 Z`,
      // Central America
      `M 160,195 L 180,205 L 190,230 L 180,255 L 165,250 L 155,225 L 160,195 Z`,
      // South America  
      `M 180,255 L 210,265 L 240,300 L 250,360 L 235,420 L 200,450 L 165,430 
       L 150,380 L 155,320 L 165,280 L 180,255 Z`,
      // Greenland
      `M 280,35 L 320,30 L 355,45 L 360,75 L 340,90 L 300,85 L 280,60 L 280,35 Z`,
    ]
  },
  EMEA: {
    center: [500, 200],
    paths: [
      // Europe
      `M 400,65 L 440,55 L 500,60 L 550,80 L 570,110 L 555,145 L 520,160 
       L 470,165 L 420,155 L 395,130 L 390,95 L 400,65 Z`,
      // UK/Ireland
      `M 375,80 L 395,75 L 405,95 L 395,115 L 375,110 L 370,95 L 375,80 Z`,
      // Scandinavia
      `M 450,35 L 480,25 L 510,40 L 515,70 L 495,85 L 465,75 L 450,50 L 450,35 Z`,
      // Middle East
      `M 540,165 L 590,160 L 630,180 L 625,220 L 590,240 L 545,230 L 530,195 L 540,165 Z`,
      // Africa
      `M 400,185 L 460,180 L 520,195 L 560,230 L 565,300 L 545,370 L 500,420 
       L 440,430 L 390,400 L 375,340 L 380,270 L 395,220 L 400,185 Z`,
      // Madagascar
      `M 575,360 L 590,355 L 600,380 L 590,415 L 575,420 L 565,395 L 575,360 Z`,
    ]
  },
  APAC: {
    center: [750, 200],
    paths: [
      // Russia/Northern Asia
      `M 570,40 L 650,30 L 760,35 L 850,50 L 900,80 L 890,115 L 840,130 
       L 760,125 L 680,115 L 610,100 L 575,70 L 570,40 Z`,
      // China/East Asia
      `M 670,125 L 740,120 L 810,140 L 830,180 L 810,220 L 760,240 
       L 700,235 L 660,210 L 655,165 L 670,125 Z`,
      // Japan
      `M 845,145 L 865,140 L 875,165 L 865,195 L 845,200 L 840,175 L 845,145 Z`,
      // India/South Asia
      `M 620,200 L 670,195 L 695,225 L 680,280 L 640,310 L 600,295 
       L 590,250 L 605,215 L 620,200 Z`,
      // Southeast Asia
      `M 700,250 L 750,255 L 790,280 L 800,320 L 780,350 L 730,355 
       L 695,330 L 690,290 L 700,250 Z`,
      // Indonesia
      `M 720,360 L 780,355 L 840,365 L 870,385 L 860,410 L 800,415 
       L 740,405 L 715,385 L 720,360 Z`,
      // Australia
      `M 770,420 L 840,410 L 900,430 L 920,480 L 890,530 L 820,545 
       L 760,525 L 745,475 L 755,440 L 770,420 Z`,
      // New Zealand
      `M 920,510 L 940,505 L 950,530 L 940,555 L 920,555 L 915,535 L 920,510 Z`,
    ]
  }
};

const REGION_CONFIG: Record<string, { name: string; color: string }> = {
  AMER: { name: 'Americas', color: '#3B82F6' },
  EMEA: { name: 'EMEA', color: '#10B981' },
  APAC: { name: 'Asia Pacific', color: '#8B5CF6' },
};

const formatValue = (value: number): string => {
  if (value >= 1000000000) return `$${(value / 1000000000).toFixed(1)}B`;
  if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
};

export function MapWidget({ widget, data, height, onClick }: MapWidgetProps) {
  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null);

  // Extract region data
  const regionData = useMemo((): RegionData[] => {
    if (data.map_data?.regions) {
      return data.map_data.regions;
    }
    if (data.series?.[0]?.data) {
      const seriesData = data.series[0].data;
      const total = seriesData.reduce((sum: number, d) => sum + (d.value || 0), 0);
      return seriesData.map(d => ({
        region: d.label || '',
        value: d.value || 0,
        percentage: total > 0 ? ((d.value || 0) / total) * 100 : 0,
      }));
    }
    return [];
  }, [data]);

  const regionDataMap = useMemo(() => {
    const map: Record<string, RegionData & { percentage: number }> = {};
    const total = regionData.reduce((sum, r) => sum + (r.value || 0), 0);
    regionData.forEach((r: RegionData) => {
      const key = r.region.toUpperCase();
      map[key] = {
        ...r,
        percentage: total > 0 ? (r.value / total) * 100 : 0
      };
    });
    return map;
  }, [regionData]);

  const total = useMemo(() => {
    if (data.map_data?.total) return data.map_data.total;
    return regionData.reduce((sum, r) => sum + (r.value || 0), 0);
  }, [data, regionData]);

  const maxValue = useMemo(() => {
    return Math.max(...regionData.map((r: RegionData) => r.value || 0), 1);
  }, [regionData]);

  const hasDrillDown = widget.interactions?.some(i => i.type === 'drill_down' && i.enabled);

  return (
    <div className="p-4 h-full flex flex-col" style={{ minHeight: height }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-slate-300">{widget.title}</h3>
        <div className="text-right">
          <span className="text-lg font-bold text-white">{formatValue(total)}</span>
          <span className="text-xs text-slate-500 ml-1">total</span>
        </div>
      </div>

      {/* Map */}
      <div className="flex-1 relative" style={{ minHeight: Math.max(height - 120, 160) }}>
        <svg 
          viewBox="0 0 960 560" 
          className="w-full h-full"
          preserveAspectRatio="xMidYMid meet"
          style={{ borderRadius: '8px', overflow: 'hidden' }}
        >
          {/* Ocean background - FIRST (bottom layer) */}
          <rect width="960" height="560" fill="#1e6091" />
          
          {/* Grid overlay for style */}
          <defs>
            <pattern id="mapGrid" width="48" height="48" patternUnits="userSpaceOnUse">
              <path d="M 48 0 L 0 0 0 48" fill="none" stroke="#2980b9" strokeWidth="0.5" opacity="0.3"/>
            </pattern>
          </defs>
          <rect width="960" height="560" fill="url(#mapGrid)" />

          {/* Continents - SECOND (middle layer) */}
          {Object.entries(REGION_PATHS).map(([regionKey, regionPathData]) => {
            const config = REGION_CONFIG[regionKey];
            const regionInfo = regionDataMap[regionKey];
            const isHovered = hoveredRegion === regionKey;
            const hasData = regionInfo && regionInfo.value > 0;
            
            // Land color - light tan/beige for visibility against blue ocean
            const landColor = hasData ? '#e8dcc8' : '#d4c4a8';
            
            return (
              <g 
                key={regionKey}
                onMouseEnter={() => setHoveredRegion(regionKey)}
                onMouseLeave={() => setHoveredRegion(null)}
                onClick={() => onClick?.(regionKey)}
                style={{ cursor: hasDrillDown ? 'pointer' : 'default' }}
              >
                {regionPathData.paths.map((path, idx) => (
                  <path
                    key={`${regionKey}-${idx}`}
                    d={path}
                    fill={landColor}
                    stroke={isHovered ? config?.color || '#666' : '#8b7355'}
                    strokeWidth={isHovered ? 2 : 1}
                    opacity={isHovered ? 1 : 0.9}
                    style={{ transition: 'all 0.2s ease' }}
                  />
                ))}
              </g>
            );
          })}

          {/* Revenue circles - THIRD (top layer) */}
          {Object.entries(REGION_PATHS).map(([regionKey, regionPathData]) => {
            const config = REGION_CONFIG[regionKey];
            const regionInfo = regionDataMap[regionKey];
            if (!regionInfo || !regionInfo.value) return null;
            
            const isHovered = hoveredRegion === regionKey;
            const [cx, cy] = regionPathData.center;
            
            // Small, opaque circles (radius 12-24 based on proportion)
            const proportion = regionInfo.value / maxValue;
            const radius = 12 + (proportion * 12);
            
            return (
              <g key={`circle-${regionKey}`}>
                {/* Circle with white border */}
                <circle
                  cx={cx}
                  cy={cy}
                  r={radius}
                  fill={config?.color || '#666'}
                  fillOpacity={1}
                  stroke="#ffffff"
                  strokeWidth={2}
                  style={{ 
                    filter: isHovered ? 'drop-shadow(0 0 6px rgba(255,255,255,0.5))' : 'none',
                    transition: 'all 0.2s ease'
                  }}
                />
                {/* Percentage label inside circle */}
                <text
                  x={cx}
                  y={cy + 4}
                  textAnchor="middle"
                  fill="#ffffff"
                  fontSize="11"
                  fontWeight="bold"
                  style={{ pointerEvents: 'none' }}
                >
                  {regionInfo.percentage.toFixed(0)}%
                </text>
              </g>
            );
          })}
        </svg>

        {/* Hover tooltip */}
        {hoveredRegion && regionDataMap[hoveredRegion] && (
          <div 
            className="absolute top-2 left-1/2 -translate-x-1/2 z-10 pointer-events-none"
            style={{
              background: 'rgba(15, 23, 42, 0.95)',
              border: `2px solid ${REGION_CONFIG[hoveredRegion]?.color || '#475569'}`,
              borderRadius: '8px',
              padding: '10px 16px',
              backdropFilter: 'blur(8px)',
              boxShadow: '0 4px 20px rgba(0,0,0,0.4)'
            }}
          >
            <div className="font-semibold text-white mb-1">
              {REGION_CONFIG[hoveredRegion]?.name}
            </div>
            <div className="flex gap-4 text-xs">
              <span className="text-slate-400">Revenue:</span>
              <span className="font-medium text-white">{formatValue(regionDataMap[hoveredRegion].value)}</span>
            </div>
            <div className="flex gap-4 text-xs">
              <span className="text-slate-400">Share:</span>
              <span className="font-semibold" style={{ color: REGION_CONFIG[hoveredRegion]?.color }}>
                {regionDataMap[hoveredRegion].percentage.toFixed(1)}%
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="flex justify-center gap-4 mt-3 p-2 bg-slate-800/40 rounded-lg">
        {Object.entries(REGION_CONFIG).map(([regionKey, config]) => {
          const regionInfo = regionDataMap[regionKey];
          const isHovered = hoveredRegion === regionKey;
          
          return (
            <div 
              key={regionKey}
              className="flex items-center gap-2 px-2 py-1 rounded transition-opacity"
              style={{
                cursor: hasDrillDown ? 'pointer' : 'default',
                opacity: hoveredRegion && !isHovered ? 0.5 : 1,
                background: isHovered ? 'rgba(255,255,255,0.05)' : 'transparent'
              }}
              onMouseEnter={() => setHoveredRegion(regionKey)}
              onMouseLeave={() => setHoveredRegion(null)}
              onClick={() => onClick?.(regionKey)}
            >
              <div 
                className="w-3 h-3 rounded-sm"
                style={{ 
                  background: config.color,
                  boxShadow: isHovered ? `0 0 8px ${config.color}` : 'none'
                }} 
              />
              <span className="text-xs text-slate-300 font-medium">{config.name}</span>
              {regionInfo && (
                <span 
                  className="text-xs font-bold ml-1"
                  style={{ color: config.color }}
                >
                  {regionInfo.percentage.toFixed(0)}%
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default MapWidget;
