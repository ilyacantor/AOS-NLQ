/**
 * MapWidget - Geographic revenue visualization with real world map using Leaflet
 *
 * Shows revenue distribution on an interactive world map (AMER, EMEA, APAC)
 * with actual country borders, pan, and zoom capabilities.
 */

import { useEffect, useRef, useMemo } from 'react';
import L from 'leaflet';
import { Widget, WidgetData } from '../../types/generated-dashboard';

interface MapWidgetProps {
  widget: Widget;
  data: WidgetData;
  height: number;
  onClick?: (value?: string) => void;
}

// Country to region mapping
const COUNTRY_REGIONS: Record<string, string> = {
  // AMER - Americas
  USA: 'AMER', CAN: 'AMER', MEX: 'AMER', BRA: 'AMER', ARG: 'AMER',
  COL: 'AMER', PER: 'AMER', VEN: 'AMER', CHL: 'AMER', ECU: 'AMER',
  BOL: 'AMER', PRY: 'AMER', URY: 'AMER', GUY: 'AMER', SUR: 'AMER',
  PAN: 'AMER', CRI: 'AMER', NIC: 'AMER', HND: 'AMER', SLV: 'AMER',
  GTM: 'AMER', BLZ: 'AMER', CUB: 'AMER', DOM: 'AMER', HTI: 'AMER',
  JAM: 'AMER', TTO: 'AMER', BHS: 'AMER', GRL: 'AMER',
  // EMEA - Europe, Middle East, Africa
  GBR: 'EMEA', DEU: 'EMEA', FRA: 'EMEA', ITA: 'EMEA', ESP: 'EMEA',
  PRT: 'EMEA', NLD: 'EMEA', BEL: 'EMEA', CHE: 'EMEA', AUT: 'EMEA',
  POL: 'EMEA', CZE: 'EMEA', HUN: 'EMEA', ROU: 'EMEA', BGR: 'EMEA',
  GRC: 'EMEA', SWE: 'EMEA', NOR: 'EMEA', FIN: 'EMEA', DNK: 'EMEA',
  IRL: 'EMEA', UKR: 'EMEA', BLR: 'EMEA', LTU: 'EMEA', LVA: 'EMEA',
  EST: 'EMEA', SVK: 'EMEA', SVN: 'EMEA', HRV: 'EMEA', SRB: 'EMEA',
  BIH: 'EMEA', MNE: 'EMEA', MKD: 'EMEA', ALB: 'EMEA', MDA: 'EMEA',
  RUS: 'EMEA', TUR: 'EMEA', ISR: 'EMEA', SAU: 'EMEA', ARE: 'EMEA',
  QAT: 'EMEA', KWT: 'EMEA', BHR: 'EMEA', OMN: 'EMEA', YEM: 'EMEA',
  JOR: 'EMEA', LBN: 'EMEA', SYR: 'EMEA', IRQ: 'EMEA', IRN: 'EMEA',
  EGY: 'EMEA', LBY: 'EMEA', TUN: 'EMEA', DZA: 'EMEA', MAR: 'EMEA',
  ZAF: 'EMEA', NGA: 'EMEA', KEN: 'EMEA', ETH: 'EMEA', GHA: 'EMEA',
  TZA: 'EMEA', UGA: 'EMEA', AGO: 'EMEA', MOZ: 'EMEA', ZWE: 'EMEA',
  ZMB: 'EMEA', BWA: 'EMEA', NAM: 'EMEA', SEN: 'EMEA', CIV: 'EMEA',
  CMR: 'EMEA', COD: 'EMEA', SDN: 'EMEA', SSD: 'EMEA', MLI: 'EMEA',
  NER: 'EMEA', TCD: 'EMEA', CAF: 'EMEA', COG: 'EMEA', GAB: 'EMEA',
  GNQ: 'EMEA', MRT: 'EMEA', ESH: 'EMEA', BFA: 'EMEA', BEN: 'EMEA',
  TGO: 'EMEA', LBR: 'EMEA', SLE: 'EMEA', GIN: 'EMEA', GMB: 'EMEA',
  GNB: 'EMEA', CPV: 'EMEA', STP: 'EMEA', MWI: 'EMEA', RWA: 'EMEA',
  BDI: 'EMEA', ERI: 'EMEA', DJI: 'EMEA', SOM: 'EMEA', MDG: 'EMEA',
  MUS: 'EMEA', SYC: 'EMEA', COM: 'EMEA', SWZ: 'EMEA', LSO: 'EMEA',
  // APAC - Asia Pacific
  CHN: 'APAC', JPN: 'APAC', KOR: 'APAC', PRK: 'APAC', TWN: 'APAC',
  HKG: 'APAC', MAC: 'APAC', MNG: 'APAC', IND: 'APAC', PAK: 'APAC',
  BGD: 'APAC', NPL: 'APAC', BTN: 'APAC', LKA: 'APAC', MDV: 'APAC',
  THA: 'APAC', VNM: 'APAC', MYS: 'APAC', SGP: 'APAC', IDN: 'APAC',
  PHL: 'APAC', MMR: 'APAC', KHM: 'APAC', LAO: 'APAC', BRN: 'APAC',
  TLS: 'APAC', AUS: 'APAC', NZL: 'APAC', PNG: 'APAC', FJI: 'APAC',
  SLB: 'APAC', VUT: 'APAC', NCL: 'APAC', WSM: 'APAC', TON: 'APAC',
  KAZ: 'APAC', UZB: 'APAC', TKM: 'APAC', KGZ: 'APAC', TJK: 'APAC',
  AFG: 'APAC',
};

// Region colors
const REGION_COLORS: Record<string, string> = {
  AMER: '#06b6d4', // cyan
  EMEA: '#8b5cf6', // purple
  APAC: '#f59e0b', // amber
  LATAM: '#10b981', // emerald
};

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
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const geoJsonLayerRef = useRef<L.GeoJSON | null>(null);

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

  // Create region lookup
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

  const hasDrillDown = widget.interactions?.some(i => i.type === 'drill_down' && i.enabled);

  // Initialize Leaflet map
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    // Create map centered on Atlantic to show all continents
    const map = L.map(mapContainerRef.current, {
      center: [20, 0],
      zoom: 1.5,
      minZoom: 1,
      maxZoom: 6,
      worldCopyJump: true,
      maxBounds: [[-90, -180], [90, 180]],
      maxBoundsViscosity: 1.0,
    });

    // Dark tile layer
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(map);

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Load and render GeoJSON countries
  useEffect(() => {
    if (!mapRef.current) return;

    const map = mapRef.current;

    // Remove existing layer if any
    if (geoJsonLayerRef.current) {
      map.removeLayer(geoJsonLayerRef.current);
    }

    // Fetch world countries GeoJSON
    fetch('https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson')
      .then(response => response.json())
      .then((geojsonData: GeoJSON.FeatureCollection) => {
        const geoJsonLayer = L.geoJSON(geojsonData, {
          style: (feature) => {
            const countryCode = feature?.properties?.ISO_A3 || '';
            const region = COUNTRY_REGIONS[countryCode];
            const regionInfo = region ? regionLookup[region] : null;
            const hasData = regionInfo && regionInfo.value > 0;
            const baseColor = region ? REGION_COLORS[region] : '#334155';

            return {
              fillColor: hasData ? baseColor : '#1e293b',
              fillOpacity: hasData ? 0.4 + (regionInfo!.percentage / 100) * 0.4 : 0.3,
              color: hasData ? baseColor : '#334155',
              weight: hasData ? 1 : 0.5,
            };
          },
          onEachFeature: (feature, layer) => {
            const countryCode = feature?.properties?.ISO_A3 || '';
            const countryName = feature?.properties?.ADMIN || countryCode;
            const region = COUNTRY_REGIONS[countryCode];
            const regionInfo = region ? regionLookup[region] : null;

            if (region && regionInfo && regionInfo.value > 0) {
              layer.bindTooltip(
                `<div style="text-align: center;">
                  <strong>${countryName}</strong><br/>
                  <span style="color: ${REGION_COLORS[region]}">${region}</span><br/>
                  ${regionInfo.percentage.toFixed(1)}% of revenue
                </div>`,
                { sticky: true }
              );

              if (hasDrillDown) {
                layer.on('click', () => {
                  onClick?.(region);
                });
              }
            } else {
              layer.bindTooltip(countryName, { sticky: true });
            }
          },
        });

        geoJsonLayer.addTo(map);
        geoJsonLayerRef.current = geoJsonLayer;
      })
      .catch(err => {
        console.error('Failed to load GeoJSON:', err);
      });

    return () => {
      if (geoJsonLayerRef.current && mapRef.current) {
        mapRef.current.removeLayer(geoJsonLayerRef.current);
        geoJsonLayerRef.current = null;
      }
    };
  }, [regionLookup, hasDrillDown, onClick]);

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-slate-400">{widget.title}</h3>
        <div className="text-right">
          <span className="text-lg font-bold text-white">{formatValue(total)}</span>
          <span className="text-xs text-slate-500 ml-1">total</span>
        </div>
      </div>

      {/* Leaflet Map Container */}
      <div
        ref={mapContainerRef}
        className="flex-1 rounded-lg overflow-hidden"
        style={{ minHeight: Math.max(height - 100, 200) }}
      />

      {/* Legend */}
      <div className="flex flex-wrap gap-3 mt-3 justify-center">
        {regionData
          .filter(r => r.value > 0)
          .sort((a, b) => (b.value || 0) - (a.value || 0))
          .map(r => {
            const regionKey = r.region?.toUpperCase() || '';
            const color = REGION_COLORS[regionKey] || '#64748b';
            return (
              <div
                key={r.region}
                className={`flex items-center gap-2 px-2 py-1 rounded ${
                  hasDrillDown ? 'cursor-pointer hover:bg-slate-800' : ''
                }`}
                onClick={() => hasDrillDown && onClick?.(r.region)}
              >
                <div
                  className="w-3 h-3 rounded-sm"
                  style={{ backgroundColor: color }}
                />
                <span className="text-xs text-slate-400">{r.region}</span>
                <span className="text-xs font-medium text-slate-300">
                  {formatValue(r.value || 0)}
                </span>
                <span className="text-xs text-slate-500">
                  ({(r.percentage || 0).toFixed(0)}%)
                </span>
              </div>
            );
          })}
      </div>
    </div>
  );
}

export default MapWidget;
