/**
 * MapWidget.tsx
 * REAL interactive map using vanilla Leaflet (works with React 19)
 * 
 * INSTALL: npm install leaflet
 * ADD TO index.html or App.tsx:
 *   <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
 * 
 * DROP INTO: src/components/dashboard/widgets/MapWidget.tsx
 */

import React, { useEffect, useRef, useState, useMemo } from 'react';
import L from 'leaflet';

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

const REGION_CONFIG: Record<string, { name: string; color: string }> = {
  AMER: { name: 'Americas', color: '#3B82F6' },
  EMEA: { name: 'EMEA', color: '#10B981' },
  APAC: { name: 'Asia Pacific', color: '#8B5CF6' },
};

// Country ISO codes to regions
const COUNTRY_REGIONS: Record<string, string> = {
  USA: 'AMER', CAN: 'AMER', MEX: 'AMER', BRA: 'AMER', ARG: 'AMER', CHL: 'AMER',
  COL: 'AMER', PER: 'AMER', VEN: 'AMER', ECU: 'AMER', BOL: 'AMER', PRY: 'AMER',
  URY: 'AMER', GUY: 'AMER', SUR: 'AMER', PAN: 'AMER', CRI: 'AMER', NIC: 'AMER',
  HND: 'AMER', SLV: 'AMER', GTM: 'AMER', BLZ: 'AMER', CUB: 'AMER', JAM: 'AMER',
  HTI: 'AMER', DOM: 'AMER', PRI: 'AMER', BHS: 'AMER', TTO: 'AMER', GRL: 'AMER',
  
  GBR: 'EMEA', DEU: 'EMEA', FRA: 'EMEA', ITA: 'EMEA', ESP: 'EMEA', PRT: 'EMEA',
  NLD: 'EMEA', BEL: 'EMEA', CHE: 'EMEA', AUT: 'EMEA', POL: 'EMEA', CZE: 'EMEA',
  HUN: 'EMEA', ROU: 'EMEA', BGR: 'EMEA', GRC: 'EMEA', SWE: 'EMEA', NOR: 'EMEA',
  DNK: 'EMEA', FIN: 'EMEA', IRL: 'EMEA', RUS: 'EMEA', UKR: 'EMEA', BLR: 'EMEA',
  TUR: 'EMEA', ARE: 'EMEA', SAU: 'EMEA', ISR: 'EMEA', JOR: 'EMEA', LBN: 'EMEA',
  IRQ: 'EMEA', IRN: 'EMEA', KWT: 'EMEA', QAT: 'EMEA', OMN: 'EMEA', BHR: 'EMEA',
  ZAF: 'EMEA', EGY: 'EMEA', MAR: 'EMEA', DZA: 'EMEA', TUN: 'EMEA', NGA: 'EMEA',
  KEN: 'EMEA', GHA: 'EMEA', TZA: 'EMEA', UGA: 'EMEA', ETH: 'EMEA', LBY: 'EMEA',
  SDN: 'EMEA', AGO: 'EMEA', MOZ: 'EMEA', ZMB: 'EMEA', ZWE: 'EMEA', BWA: 'EMEA',
  NAM: 'EMEA', SEN: 'EMEA', CIV: 'EMEA', CMR: 'EMEA', COD: 'EMEA', MDG: 'EMEA',
  
  CHN: 'APAC', JPN: 'APAC', KOR: 'APAC', IND: 'APAC', AUS: 'APAC', NZL: 'APAC',
  IDN: 'APAC', MYS: 'APAC', SGP: 'APAC', THA: 'APAC', VNM: 'APAC', PHL: 'APAC',
  PAK: 'APAC', BGD: 'APAC', LKA: 'APAC', MMR: 'APAC', KHM: 'APAC', LAO: 'APAC',
  TWN: 'APAC', HKG: 'APAC', MNG: 'APAC', PRK: 'APAC', NPL: 'APAC', BTN: 'APAC',
  AFG: 'APAC', KAZ: 'APAC', UZB: 'APAC', TKM: 'APAC', KGZ: 'APAC', TJK: 'APAC',
  AZE: 'APAC', ARM: 'APAC', GEO: 'APAC', PNG: 'APAC', FJI: 'APAC',
};

const formatCurrency = (value: number): string => {
  if (value >= 1000000000) return `$${(value / 1000000000).toFixed(1)}B`;
  if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
};

export const MapWidget: React.FC<MapWidgetProps> = ({ schema, data }) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
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

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    // Initialize map
    const map = L.map(mapContainer.current, {
      center: [20, 0],
      zoom: 1.5,
      minZoom: 1,
      maxZoom: 6,
      zoomControl: false,
      attributionControl: false,
    });

    mapRef.current = map;

    // Add tile layer (using CartoDB's light theme for clean look)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
    }).addTo(map);

    // Load country boundaries GeoJSON
    fetch('https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson')
      .then(res => res.json())
      .then(geojson => {
        L.geoJSON(geojson, {
          style: (feature) => {
            const iso = feature?.properties?.ISO_A3;
            const region = COUNTRY_REGIONS[iso];
            const config = region ? REGION_CONFIG[region] : null;
            
            return {
              fillColor: config ? config.color : '#94a3b8',
              fillOpacity: config ? 0.6 : 0.1,
              color: '#ffffff',
              weight: 0.5,
            };
          },
          onEachFeature: (feature, layer) => {
            const iso = feature?.properties?.ISO_A3;
            const region = COUNTRY_REGIONS[iso];
            
            if (region) {
              layer.on({
                mouseover: () => setHoveredRegion(region),
                mouseout: () => setHoveredRegion(null),
              });
            }
          }
        }).addTo(map);
      });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  return (
    <div style={{
      background: '#ffffff',
      borderRadius: '12px',
      padding: '16px',
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    }}>
      {/* Header */}
      <div style={{ marginBottom: '12px' }}>
        <h3 style={{ color: '#1e293b', fontSize: '15px', fontWeight: 600, margin: 0 }}>
          {schema.title || 'Revenue by Region'}
        </h3>
        <p style={{ color: '#64748b', fontSize: '12px', margin: '4px 0 0 0' }}>
          Total: {formatCurrency(total)}
        </p>
      </div>

      {/* Map */}
      <div style={{ flex: 1, position: 'relative', minHeight: '200px', borderRadius: '8px', overflow: 'hidden' }}>
        <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />
        
        {/* Tooltip */}
        {hoveredRegion && regionDataMap[hoveredRegion] && (
          <div style={{
            position: 'absolute',
            top: '10px',
            left: '50%',
            transform: 'translateX(-50%)',
            background: 'white',
            border: `2px solid ${REGION_CONFIG[hoveredRegion]?.color}`,
            borderRadius: '8px',
            padding: '12px 16px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            zIndex: 1000,
          }}>
            <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: '4px' }}>
              {REGION_CONFIG[hoveredRegion]?.name}
            </div>
            <div style={{ fontSize: '13px', color: '#64748b' }}>
              Revenue: <strong style={{ color: '#1e293b' }}>{formatCurrency(regionDataMap[hoveredRegion].value)}</strong>
            </div>
            <div style={{ fontSize: '13px', color: '#64748b' }}>
              Share: <strong style={{ color: REGION_CONFIG[hoveredRegion]?.color }}>{regionDataMap[hoveredRegion].percentage.toFixed(1)}%</strong>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        gap: '24px',
        marginTop: '12px',
      }}>
        {Object.entries(REGION_CONFIG).map(([regionKey, config]) => {
          const regionData = regionDataMap[regionKey];
          
          return (
            <div 
              key={regionKey}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                cursor: 'pointer',
                opacity: hoveredRegion && hoveredRegion !== regionKey ? 0.5 : 1,
              }}
              onMouseEnter={() => setHoveredRegion(regionKey)}
              onMouseLeave={() => setHoveredRegion(null)}
            >
              <div style={{
                width: '14px',
                height: '14px',
                borderRadius: '4px',
                background: config.color,
              }} />
              <span style={{ color: '#475569', fontSize: '13px', fontWeight: 500 }}>
                {config.name}
              </span>
              {regionData && (
                <span style={{ color: config.color, fontSize: '13px', fontWeight: 700 }}>
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
