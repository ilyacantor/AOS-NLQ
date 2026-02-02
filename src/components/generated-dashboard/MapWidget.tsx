/**
 * MapWidget - Geographic revenue visualization with interactive world map
 *
 * Shows revenue distribution on an interactive world map with:
 * - Solid ocean background (no distracting tiles)
 * - Countries colored by region (AMER, EMEA, APAC)
 * - Revenue bubbles sized by amount
 * - Pan and zoom capabilities
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

// Country to region mapping (ISO_A3 codes)
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

// Region colors - vibrant but professional
const REGION_COLORS: Record<string, string> = {
  AMER: '#3b82f6', // blue
  EMEA: '#8b5cf6', // purple
  APAC: '#f59e0b', // amber
  LATAM: '#10b981', // emerald
};

// Region center coordinates for bubble placement
const REGION_CENTERS: Record<string, [number, number]> = {
  AMER: [39.8, -98.5],   // Central USA
  EMEA: [48.5, 15],      // Central Europe
  APAC: [25, 105],       // East Asia
  LATAM: [-15, -55],     // Central South America
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
  const bubblesLayerRef = useRef<L.LayerGroup | null>(null);

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

  // Calculate max value for bubble scaling
  const maxValue = useMemo(() => {
    return Math.max(...regionData.map(r => r.value || 0), 1);
  }, [regionData]);

  // Initialize Leaflet map with solid background
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
      attributionControl: false,
      zoomControl: true,
    });

    // Set solid ocean background via CSS - bright ocean blue
    mapContainerRef.current.style.backgroundColor = '#1e6091';

    // Create custom pane for bubbles with higher z-index than overlayPane (400)
    map.createPane('bubblesPane');
    const bubblesPane = map.getPane('bubblesPane');
    if (bubblesPane) {
      bubblesPane.style.zIndex = '450';
    }

    mapRef.current = map;

    // Create layer group for bubbles
    bubblesLayerRef.current = L.layerGroup().addTo(map);

    return () => {
      map.remove();
      mapRef.current = null;
      bubblesLayerRef.current = null;
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
          style: () => {
            // Neutral land masses - no colored overlay
            return {
              fillColor: '#2d4a3e',
              fillOpacity: 0.9,
              color: '#1a3a2e',
              weight: 0.5,
            };
          },
          onEachFeature: (feature, layer) => {
            const countryCode = feature?.properties?.ISO_A3 || '';
            const countryName = feature?.properties?.ADMIN || countryCode;
            const region = COUNTRY_REGIONS[countryCode];
            const regionInfo = region ? regionLookup[region] : null;

            if (region && regionInfo && regionInfo.value > 0) {
              layer.bindTooltip(
                `<div style="text-align: center; font-size: 12px;">
                  <strong>${countryName}</strong><br/>
                  <span style="color: ${REGION_COLORS[region]}; font-weight: 600;">${region}</span>
                </div>`,
                { sticky: true, className: 'map-tooltip' }
              );
            } else if (region) {
              layer.bindTooltip(
                `<div style="text-align: center; font-size: 12px;">
                  <strong>${countryName}</strong><br/>
                  <span style="color: #64748b;">${region}</span>
                </div>`,
                { sticky: true, className: 'map-tooltip' }
              );
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
  }, [regionLookup]);

  // Add revenue bubbles
  useEffect(() => {
    if (!mapRef.current || !bubblesLayerRef.current) return;

    const bubblesLayer = bubblesLayerRef.current;
    bubblesLayer.clearLayers();

    // Add bubble for each region with data
    regionData.forEach(r => {
      const regionKey = r.region?.toUpperCase() || '';
      const center = REGION_CENTERS[regionKey];
      if (!center || !r.value) return;

      const color = REGION_COLORS[regionKey] || '#64748b';

      // Scale radius: min 10, max 28 based on value proportion (smaller, cleaner)
      const proportion = r.value / maxValue;
      const radius = 10 + (proportion * 18);

      // Create circle marker in custom pane to ensure it's above countries
      const circle = L.circleMarker(center, {
        radius: radius,
        fillColor: color,
        fillOpacity: 0.8,
        color: '#ffffff',
        weight: 2,
        pane: 'bubblesPane',
        className: 'revenue-bubble',
      });

      // Add tooltip with value
      circle.bindTooltip(
        `<div style="text-align: center; padding: 4px;">
          <div style="font-weight: 700; font-size: 14px; color: ${color};">${regionKey}</div>
          <div style="font-size: 16px; font-weight: 700; color: #fff;">${formatValue(r.value)}</div>
          <div style="font-size: 11px; color: #94a3b8;">${(r.percentage || 0).toFixed(1)}% of total</div>
        </div>`,
        {
          permanent: false,
          direction: 'top',
          offset: [0, -radius],
          className: 'bubble-tooltip'
        }
      );

      // Add click handler for drill-down
      if (hasDrillDown) {
        circle.on('click', (e) => {
          L.DomEvent.stopPropagation(e);
          onClick?.(regionKey);
        });
        circle.getElement?.()?.style.setProperty('cursor', 'pointer');
      }

      circle.addTo(bubblesLayer);

      // Add permanent label inside bubble
      const label = L.divIcon({
        className: 'bubble-label',
        html: `<div style="
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          width: ${radius * 2}px;
          height: ${radius * 2}px;
          margin-left: -${radius}px;
          margin-top: -${radius}px;
          color: white;
          text-shadow: 0 1px 2px rgba(0,0,0,0.5);
          pointer-events: none;
          font-family: system-ui, sans-serif;
        ">
          <div style="font-size: ${Math.max(10, radius / 3)}px; font-weight: 700;">${formatValue(r.value)}</div>
          <div style="font-size: ${Math.max(8, radius / 4)}px; opacity: 0.9;">${regionKey}</div>
        </div>`,
        iconSize: [radius * 2, radius * 2],
      });

      L.marker(center, { icon: label, interactive: false }).addTo(bubblesLayer);
    });
  }, [regionData, maxValue, hasDrillDown, onClick]);

  return (
    <div
      className="p-4 h-full flex flex-col"
      onMouseDown={(e) => e.stopPropagation()}
      onTouchStart={(e) => e.stopPropagation()}
    >
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
                  className="w-3 h-3 rounded-full"
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
