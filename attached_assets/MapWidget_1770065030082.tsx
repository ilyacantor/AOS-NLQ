/**
 * MapWidget.tsx
 * Real world map using embedded SVG paths - NO EXTERNAL DEPENDENCIES
 * Works with React 19
 * 
 * DROP INTO: src/components/dashboard/widgets/MapWidget.tsx
 */

import React, { useState, useMemo } from 'react';

interface RegionData {
  region: string;
  value: number;
  percentage?: number;
}

interface MapWidgetProps {
  schema: {
    id: string;
    title?: string;
    data_binding?: {
      metric?: string;
      dimension?: string;
    };
  };
  data: {
    regions?: RegionData[];
    total?: number;
    metric_name?: string;
    currency?: string;
  };
}

// Simplified but recognizable continent/region paths
const REGION_PATHS: Record<string, { paths: string[]; label: string; labelPos: [number, number] }> = {
  AMER: {
    label: 'Americas',
    labelPos: [150, 280],
    paths: [
      // North America
      `M 120,50 L 140,45 L 180,50 L 220,55 L 260,70 L 280,90 L 270,110 L 250,130 
       L 230,140 L 210,155 L 200,170 L 190,165 L 180,170 L 165,165 L 150,175 
       L 140,185 L 130,180 L 120,170 L 100,165 L 85,150 L 75,130 L 70,110 
       L 75,90 L 85,75 L 100,60 L 120,50 Z`,
      // Central America
      `M 165,175 L 175,180 L 185,195 L 190,210 L 185,225 L 175,235 L 165,230 
       L 160,220 L 155,205 L 160,190 L 165,175 Z`,
      // South America
      `M 185,235 L 200,240 L 220,250 L 235,270 L 240,300 L 235,340 L 225,380 
       L 210,420 L 195,450 L 180,470 L 170,460 L 165,430 L 170,390 L 175,350 
       L 170,310 L 165,280 L 170,260 L 180,245 L 185,235 Z`,
      // Greenland
      `M 280,30 L 310,25 L 340,35 L 350,55 L 340,75 L 320,80 L 295,75 L 280,60 L 280,30 Z`,
    ]
  },
  EMEA: {
    label: 'EMEA',
    labelPos: [480, 200],
    paths: [
      // Europe
      `M 380,70 L 400,65 L 430,60 L 470,65 L 510,75 L 540,90 L 560,100 
       L 555,120 L 540,135 L 520,145 L 490,150 L 460,145 L 430,150 
       L 400,145 L 380,140 L 370,125 L 375,105 L 380,85 L 380,70 Z`,
      // UK/Ireland
      `M 360,85 L 375,80 L 385,90 L 380,105 L 365,110 L 355,100 L 360,85 Z`,
      // Scandinavia
      `M 420,35 L 440,30 L 465,40 L 475,60 L 465,75 L 445,70 L 430,55 L 420,35 Z`,
      // Middle East
      `M 520,160 L 560,155 L 590,165 L 600,190 L 590,215 L 560,225 
       L 530,220 L 510,200 L 515,175 L 520,160 Z`,
      // Africa
      `M 380,180 L 420,175 L 460,180 L 500,190 L 530,210 L 540,250 
       L 535,300 L 520,350 L 495,400 L 460,430 L 420,440 L 385,420 
       L 365,380 L 360,330 L 365,280 L 375,230 L 380,180 Z`,
      // Madagascar
      `M 545,380 L 555,375 L 565,390 L 560,420 L 545,430 L 535,415 L 540,390 L 545,380 Z`,
    ]
  },
  APAC: {
    label: 'Asia Pacific',
    labelPos: [720, 200],
    paths: [
      // Russia/Northern Asia
      `M 560,50 L 620,40 L 700,35 L 780,40 L 850,50 L 880,70 L 870,95 
       L 840,110 L 790,115 L 730,110 L 670,105 L 620,95 L 580,85 L 560,70 L 560,50 Z`,
      // China/East Asia
      `M 650,110 L 700,105 L 760,115 L 800,130 L 810,160 L 795,190 
       L 760,210 L 720,215 L 680,205 L 650,185 L 640,155 L 645,130 L 650,110 Z`,
      // Japan
      `M 820,130 L 835,125 L 845,140 L 840,165 L 825,175 L 815,160 L 820,130 Z`,
      // Southeast Asia
      `M 680,220 L 720,225 L 760,235 L 780,260 L 770,290 L 740,305 
       L 700,300 L 670,280 L 665,250 L 680,220 Z`,
      // India
      `M 600,180 L 640,175 L 660,195 L 655,230 L 635,270 L 610,290 
       L 585,280 L 575,250 L 580,215 L 595,190 L 600,180 Z`,
      // Indonesia
      `M 700,310 L 740,305 L 780,315 L 820,320 L 840,335 L 830,350 
       L 790,355 L 750,350 L 710,340 L 695,325 L 700,310 Z`,
      // Australia
      `M 740,380 L 790,370 L 840,380 L 870,400 L 875,440 L 860,480 
       L 820,500 L 770,495 L 735,470 L 720,430 L 725,395 L 740,380 Z`,
      // New Zealand
      `M 890,480 L 905,475 L 915,490 L 910,515 L 895,525 L 880,515 L 885,495 L 890,480 Z`,
      // Philippines
      `M 790,250 L 805,245 L 815,260 L 810,285 L 795,295 L 785,280 L 790,250 Z`,
      // Taiwan
      `M 795,195 L 805,190 L 810,205 L 800,215 L 790,210 L 795,195 Z`,
    ]
  }
};

const REGION_CONFIG: Record<string, { name: string; color: string }> = {
  AMER: { name: 'Americas', color: '#3B82F6' },
  EMEA: { name: 'EMEA', color: '#10B981' },
  APAC: { name: 'Asia Pacific', color: '#8B5CF6' },
};

const formatCurrency = (value: number): string => {
  if (value >= 1000000000) return `$${(value / 1000000000).toFixed(1)}B`;
  if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
};

export const MapWidget: React.FC<MapWidgetProps> = ({ schema, data }) => {
  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null);

  const regionDataMap = useMemo(() => {
    const map: Record<string, RegionData & { percentage: number }> = {};
    if (data?.regions) {
      const total = data.total || data.regions.reduce((sum, r) => sum + r.value, 0);
      data.regions.forEach(r => {
        map[r.region.toUpperCase()] = {
          ...r,
          percentage: total > 0 ? (r.value / total) * 100 : 0
        };
      });
    }
    return map;
  }, [data]);

  const total = data?.total || (data?.regions?.reduce((sum, r) => sum + r.value, 0) || 0);

  const getRegionStyle = (regionKey: string) => {
    const config = REGION_CONFIG[regionKey];
    const regionData = regionDataMap[regionKey];
    const isHovered = hoveredRegion === regionKey;
    
    if (!config) return { fill: '#334155', opacity: 0.5 };
    
    // Calculate opacity based on percentage (min 0.4, max 1.0)
    const baseOpacity = regionData 
      ? Math.max(0.5, Math.min(1, 0.4 + (regionData.percentage / 100)))
      : 0.4;
    
    return {
      fill: config.color,
      opacity: isHovered ? 1 : baseOpacity,
      filter: isHovered ? 'brightness(1.2)' : 'none',
    };
  };

  return (
    <div style={{
      background: 'linear-gradient(145deg, #0c1222 0%, #1a2744 100%)',
      borderRadius: '12px',
      padding: '16px',
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    }}>
      {/* Header */}
      <div style={{ marginBottom: '12px' }}>
        <h3 style={{ 
          color: '#f1f5f9', 
          fontSize: '15px', 
          fontWeight: 600, 
          margin: 0,
          letterSpacing: '-0.01em'
        }}>
          {schema.title || 'Revenue by Region'}
        </h3>
        <p style={{ color: '#64748b', fontSize: '12px', margin: '4px 0 0 0' }}>
          Total: {formatCurrency(total)}
        </p>
      </div>

      {/* Map Container */}
      <div style={{ flex: 1, position: 'relative', minHeight: '180px' }}>
        <svg 
          viewBox="0 0 960 540" 
          style={{ 
            width: '100%', 
            height: '100%',
          }}
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Ocean/background */}
          <rect width="960" height="540" fill="#0f172a" />
          
          {/* Grid lines for style */}
          <defs>
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e3a5f" strokeWidth="0.5" opacity="0.3"/>
            </pattern>
            <filter id="glow">
              <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
              <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>
          <rect width="960" height="540" fill="url(#grid)" />

          {/* Render each region */}
          {Object.entries(REGION_PATHS).map(([regionKey, regionData]) => {
            const style = getRegionStyle(regionKey);
            const isHovered = hoveredRegion === regionKey;
            
            return (
              <g 
                key={regionKey}
                onMouseEnter={() => setHoveredRegion(regionKey)}
                onMouseLeave={() => setHoveredRegion(null)}
                style={{ cursor: 'pointer' }}
              >
                {regionData.paths.map((path, idx) => (
                  <path
                    key={`${regionKey}-${idx}`}
                    d={path}
                    fill={style.fill}
                    opacity={style.opacity}
                    stroke={isHovered ? '#fff' : '#1e293b'}
                    strokeWidth={isHovered ? 1.5 : 0.5}
                    filter={isHovered ? 'url(#glow)' : undefined}
                    style={{ transition: 'all 0.2s ease-out' }}
                  />
                ))}
              </g>
            );
          })}
        </svg>

        {/* Hover tooltip */}
        {hoveredRegion && regionDataMap[hoveredRegion] && (
          <div style={{
            position: 'absolute',
            top: '8px',
            left: '50%',
            transform: 'translateX(-50%)',
            background: 'rgba(15, 23, 42, 0.95)',
            border: `1px solid ${REGION_CONFIG[hoveredRegion]?.color || '#475569'}`,
            borderRadius: '8px',
            padding: '10px 14px',
            color: '#f8fafc',
            fontSize: '13px',
            pointerEvents: 'none',
            zIndex: 10,
            backdropFilter: 'blur(8px)',
            boxShadow: '0 4px 20px rgba(0,0,0,0.3)'
          }}>
            <div style={{ fontWeight: 600, marginBottom: '4px' }}>
              {REGION_CONFIG[hoveredRegion]?.name}
            </div>
            <div style={{ display: 'flex', gap: '16px', fontSize: '12px' }}>
              <span style={{ color: '#94a3b8' }}>Revenue:</span>
              <span style={{ fontWeight: 500 }}>{formatCurrency(regionDataMap[hoveredRegion].value)}</span>
            </div>
            <div style={{ display: 'flex', gap: '16px', fontSize: '12px' }}>
              <span style={{ color: '#94a3b8' }}>Share:</span>
              <span style={{ fontWeight: 500, color: REGION_CONFIG[hoveredRegion]?.color }}>
                {regionDataMap[hoveredRegion].percentage.toFixed(1)}%
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        gap: '20px',
        marginTop: '12px',
        padding: '10px',
        background: 'rgba(30, 41, 59, 0.4)',
        borderRadius: '8px'
      }}>
        {Object.entries(REGION_CONFIG).map(([regionKey, config]) => {
          const regionData = regionDataMap[regionKey];
          const isHovered = hoveredRegion === regionKey;
          
          return (
            <div 
              key={regionKey}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                cursor: 'pointer',
                opacity: hoveredRegion && !isHovered ? 0.5 : 1,
                transition: 'opacity 0.2s',
                padding: '4px 8px',
                borderRadius: '4px',
                background: isHovered ? 'rgba(255,255,255,0.05)' : 'transparent'
              }}
              onMouseEnter={() => setHoveredRegion(regionKey)}
              onMouseLeave={() => setHoveredRegion(null)}
            >
              <div style={{
                width: '12px',
                height: '12px',
                borderRadius: '3px',
                background: config.color,
                boxShadow: isHovered ? `0 0 8px ${config.color}` : 'none'
              }} />
              <span style={{ color: '#cbd5e1', fontSize: '12px', fontWeight: 500 }}>
                {config.name}
              </span>
              {regionData && (
                <span style={{ 
                  color: config.color, 
                  fontSize: '12px', 
                  fontWeight: 600,
                  marginLeft: '4px'
                }}>
                  {regionData.percentage.toFixed(0)}%
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default MapWidget;
