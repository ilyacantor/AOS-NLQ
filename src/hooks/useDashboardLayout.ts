// *Last updated: 2026-02-07*

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import type { Layout } from 'react-grid-layout';
import { DashboardSchema } from '../types/generated-dashboard';

export type LayoutItem = {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
};

interface UseDashboardLayoutProps {
  schema: DashboardSchema | null;
  setSchema: React.Dispatch<React.SetStateAction<DashboardSchema | null>>;
}

interface UseDashboardLayoutReturn {
  layoutMap: Record<string, LayoutItem>;
  setLayoutMap: React.Dispatch<React.SetStateAction<Record<string, LayoutItem>>>;
  containerRef: React.RefObject<HTMLDivElement | null>;
  containerWidth: number;
  editMode: boolean;
  setEditMode: React.Dispatch<React.SetStateAction<boolean>>;
  gridLayout: LayoutItem[];
  handleLayoutChange: (newLayout: Layout[]) => void;
  handleAutoArrange: () => void;
}

export function useDashboardLayout({
  schema,
  setSchema,
}: UseDashboardLayoutProps): UseDashboardLayoutReturn {
  const [layoutMap, setLayoutMap] = useState<Record<string, LayoutItem>>({});
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(1200);
  const [editMode, setEditMode] = useState(false);
  const editModeRef = useRef(false);
  editModeRef.current = editMode;

  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.offsetWidth - 48);
      }
    };
    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

  // Max col span = half the grid so two widgets always fit side by side
  const halfGrid = Math.floor((schema?.layout.columns || 12) / 2);
  const MAX_COL_SPAN: Record<string, number> = {
    map: halfGrid,
    line_chart: halfGrid,
    bar_chart: halfGrid,
    area_chart: halfGrid,
    stacked_bar: halfGrid,
    donut_chart: halfGrid,
    horizontal_bar: halfGrid,
    data_table: halfGrid,
  };

  const maxSpanForType = (type: string) => {
    if (type === 'kpi_card') return 2;
    if (type === 'data_table') return 5;
    if (type === 'map') return 3;
    return 4; // charts
  };

  const gridLayout = useMemo((): LayoutItem[] => {
    if (!schema) return [];

    return schema.widgets.map(widget => {
      const stored = layoutMap[widget.id];
      if (stored) {
        return { ...stored, i: widget.id };
      }
      const maxH = maxSpanForType(widget.type);
      return {
        i: widget.id,
        x: widget.position.column - 1,
        y: widget.position.row - 1,
        w: widget.position.col_span,
        h: Math.min(widget.position.row_span, maxH),
        minW: 2,
        minH: 2,
      };
    });
  }, [schema, layoutMap]);

  const handleLayoutChange = useCallback((newLayout: Layout[]) => {
    if (!editModeRef.current) {
      return;
    }

    setLayoutMap(prevMap => {
      const newMap: Record<string, LayoutItem> = { ...prevMap };
      let changed = false;
      newLayout.forEach(item => {
        const prev = prevMap[item.i];
        if (!prev || prev.x !== item.x || prev.y !== item.y || prev.w !== item.w || prev.h !== item.h) {
          changed = true;
        }
        newMap[item.i] = item;
      });
      return changed ? newMap : prevMap;
    });

    setSchema(prevSchema => {
      if (!prevSchema) return prevSchema;
      let anyPositionChanged = false;
      const updatedWidgets = prevSchema.widgets.map(widget => {
        const layoutItem = newLayout.find(l => l.i === widget.id);
        if (layoutItem) {
          const newCol = layoutItem.x + 1;
          const newRow = layoutItem.y + 1;
          const newColSpan = layoutItem.w;
          const newRowSpan = layoutItem.h;
          if (
            widget.position.column !== newCol ||
            widget.position.row !== newRow ||
            widget.position.col_span !== newColSpan ||
            widget.position.row_span !== newRowSpan
          ) {
            anyPositionChanged = true;
            return {
              ...widget,
              position: {
                ...widget.position,
                column: newCol,
                row: newRow,
                col_span: newColSpan,
                row_span: newRowSpan,
              },
            };
          }
        }
        return widget;
      });
      if (!anyPositionChanged) return prevSchema;
      return { ...prevSchema, widgets: updatedWidgets };
    });
  }, []);

  const handleAutoArrange = useCallback(() => {
    // Clear layoutMap so gridLayout reads from schema positions (no stale overrides)
    setLayoutMap({});

    setSchema(prevSchema => {
      if (!prevSchema) return prevSchema;

      const cols = prevSchema.layout.columns;

      // ----- Categorise widgets by type -----
      const kpis = prevSchema.widgets.filter(w => w.type === 'kpi_card');
      const charts = prevSchema.widgets.filter(w =>
        ['line_chart', 'bar_chart', 'area_chart', 'stacked_bar', 'donut_chart', 'horizontal_bar'].includes(w.type)
      );
      const maps = prevSchema.widgets.filter(w => w.type === 'map');
      const tables = prevSchema.widgets.filter(w => w.type === 'data_table');
      const others = prevSchema.widgets.filter(w =>
        !['kpi_card', 'line_chart', 'bar_chart', 'area_chart', 'stacked_bar', 'donut_chart', 'horizontal_bar', 'data_table', 'map'].includes(w.type)
      );

      // ----- Grid helpers -----
      const grid: boolean[][] = [];
      const getRow = (y: number) => {
        while (grid.length <= y) grid.push(new Array(cols).fill(false));
        return grid[y];
      };

      const canPlace = (x: number, y: number, w: number, h: number): boolean => {
        if (x + w > cols) return false;
        for (let dy = 0; dy < h; dy++) {
          const row = getRow(y + dy);
          for (let dx = 0; dx < w; dx++) {
            if (row[x + dx]) return false;
          }
        }
        return true;
      };

      const placeOnGrid = (x: number, y: number, w: number, h: number) => {
        for (let dy = 0; dy < h; dy++) {
          const row = getRow(y + dy);
          for (let dx = 0; dx < w; dx++) {
            row[x + dx] = true;
          }
        }
      };

      const findPosition = (w: number, h: number): { x: number; y: number } => {
        for (let y = 0; ; y++) {
          for (let x = 0; x <= cols - w; x++) {
            if (canPlace(x, y, w, h)) {
              return { x, y };
            }
          }
        }
      };

      // ----- KPIs: evenly divide across the row -----
      const placed: Record<string, LayoutItem> = {};

      if (kpis.length > 0) {
        const kpiH = 2; // Compact KPI height
        const baseW = Math.floor(cols / kpis.length);
        const extra = cols % kpis.length;
        let x = 0;
        kpis.forEach((widget, idx) => {
          const w = baseW + (idx < extra ? 1 : 0);
          placeOnGrid(x, 0, w, kpiH);
          placed[widget.id] = { i: widget.id, x, y: 0, w, h: kpiH, minW: 2, minH: 2 };
          x += w;
        });
      }

      // ----- Place maps, charts, tables, others with bin-packing -----
      const placeGroup = (widgets: typeof charts, defaultW: number, defaultH: number, maxH: number) => {
        widgets.forEach(widget => {
          const maxW = MAX_COL_SPAN[widget.type];
          const w = Math.min(maxW || widget.position.col_span || defaultW, cols);
          const h = Math.min(widget.position.row_span || defaultH, maxH);
          const pos = findPosition(w, h);
          placeOnGrid(pos.x, pos.y, w, h);
          placed[widget.id] = { i: widget.id, x: pos.x, y: pos.y, w, h, minW: 2, minH: 2 };
        });
      };

      placeGroup(maps, 6, 3, 3);
      placeGroup(charts, 6, 4, 4);
      placeGroup(tables, 4, 4, 5);
      placeGroup(others, 3, 2, 4);

      // ----- Gap-fill pass: expand widgets to eliminate dark space -----
      const items = Object.values(placed).sort((a, b) => a.y - b.y || a.x - b.x);

      // Build occupancy grid (id-based)
      let maxRow = 0;
      items.forEach(item => { if (item.y + item.h > maxRow) maxRow = item.y + item.h; });

      const occ: (string | null)[][] = [];
      for (let r = 0; r < maxRow; r++) occ.push(new Array(cols).fill(null));
      items.forEach(item => {
        for (let dy = 0; dy < item.h; dy++)
          for (let dx = 0; dx < item.w; dx++)
            occ[item.y + dy][item.x + dx] = item.i;
      });

      // Build widget type lookup for gap-fill constraints
      const widgetTypeMap: Record<string, string> = {};
      prevSchema.widgets.forEach(w => { widgetTypeMap[w.id] = w.type; });

      // Expand rightward (respect per-type max col span; skip KPIs — they're already evenly distributed)
      items.forEach(item => {
        const wType = widgetTypeMap[item.i] || '';
        if (wType === 'kpi_card') return; // KPIs stay at their initial even width
        const maxW = MAX_COL_SPAN[wType];
        while (item.x + item.w < cols) {
          if (maxW && item.w >= maxW) break;
          let ok = true;
          for (let dy = 0; dy < item.h; dy++) {
            if (occ[item.y + dy][item.x + item.w] !== null) { ok = false; break; }
          }
          if (!ok) break;
          for (let dy = 0; dy < item.h; dy++) occ[item.y + dy][item.x + item.w] = item.i;
          item.w++;
        }
      });

      // Expand downward (bounded by maxRow; skip KPIs)
      items.forEach(item => {
        const wType2 = widgetTypeMap[item.i] || '';
        if (wType2 === 'kpi_card') return;
        while (item.y + item.h < maxRow) {
          const nr = item.y + item.h;
          let ok = true;
          for (let dx = 0; dx < item.w; dx++) {
            if (occ[nr][item.x + dx] !== null) { ok = false; break; }
          }
          if (!ok) break;
          for (let dx = 0; dx < item.w; dx++) occ[nr][item.x + dx] = item.i;
          item.h++;
        }
      });

      // ----- Write expanded positions back into schema -----
      const updatedWidgets = prevSchema.widgets.map(widget => {
        const p = placed[widget.id];
        if (p) {
          return {
            ...widget,
            position: { ...widget.position, column: p.x + 1, row: p.y + 1, col_span: p.w, row_span: p.h },
          };
        }
        return widget;
      });

      return { ...prevSchema, widgets: updatedWidgets };
    });
  }, []);

  return {
    layoutMap,
    setLayoutMap,
    containerRef,
    containerWidth,
    editMode,
    setEditMode,
    gridLayout,
    handleLayoutChange,
    handleAutoArrange,
  };
}
