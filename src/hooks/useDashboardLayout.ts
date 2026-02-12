// *Last updated: 2026-02-07*

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
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
  handleLayoutChange: (newLayout: LayoutItem[]) => void;
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

  const gridLayout = useMemo((): LayoutItem[] => {
    if (!schema) return [];

    return schema.widgets.map(widget => {
      const stored = layoutMap[widget.id];
      if (stored) {
        return { ...stored, i: widget.id };
      }
      return {
        i: widget.id,
        x: widget.position.column - 1,
        y: widget.position.row - 1,
        w: widget.position.col_span,
        h: widget.position.row_span,
        minW: 2,
        minH: 2,
      };
    });
  }, [schema, layoutMap]);

  const handleLayoutChange = useCallback((newLayout: LayoutItem[]) => {
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
    setSchema(prevSchema => {
      if (!prevSchema) return prevSchema;

      const cols = prevSchema.layout.columns;

      // ----- Categorise widgets by type -----
      const kpis = prevSchema.widgets.filter(w => w.type === 'kpi_card');
      const charts = prevSchema.widgets.filter(w =>
        ['line_chart', 'bar_chart', 'area_chart', 'stacked_bar', 'donut_chart', 'horizontal_bar'].includes(w.type)
      );
      const tables = prevSchema.widgets.filter(w => w.type === 'data_table');
      const others = prevSchema.widgets.filter(w =>
        !['kpi_card', 'line_chart', 'bar_chart', 'area_chart', 'stacked_bar', 'donut_chart', 'horizontal_bar', 'data_table'].includes(w.type)
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

      const newLayoutMap: Record<string, LayoutItem> = {};

      // ----- KPIs: evenly divide across the row -----
      if (kpis.length > 0) {
        const kpiH = kpis[0].position.row_span || 2;
        // Find first row with enough space (should be row 0)
        const startY = 0;
        const baseW = Math.floor(cols / kpis.length);
        const extra = cols % kpis.length;
        let x = 0;
        kpis.forEach((widget, idx) => {
          const w = baseW + (idx < extra ? 1 : 0);
          placeOnGrid(x, startY, w, kpiH);
          newLayoutMap[widget.id] = { i: widget.id, x, y: startY, w, h: kpiH, minW: 2, minH: 2 };
          x += w;
        });
      }

      // ----- Place charts, tables, others with bin-packing -----
      const placeGroup = (widgets: typeof charts, defaultW: number, defaultH: number) => {
        widgets.forEach(widget => {
          const w = Math.min(widget.position.col_span || defaultW, cols);
          const h = widget.position.row_span || defaultH;
          const pos = findPosition(w, h);
          placeOnGrid(pos.x, pos.y, w, h);
          newLayoutMap[widget.id] = { i: widget.id, x: pos.x, y: pos.y, w, h, minW: 2, minH: 2 };
        });
      };

      placeGroup(charts, 6, 3);
      placeGroup(tables, 4, 3);
      placeGroup(others, 3, 2);

      // ----- Gap-fill pass: expand widgets to eliminate dark space -----
      // Process widgets top-to-bottom, left-to-right
      const items = Object.values(newLayoutMap).sort((a, b) => a.y - b.y || a.x - b.x);

      // Rebuild a clean occupancy grid using widget IDs
      const occGrid: (string | null)[][] = [];
      const ensureRow = (y: number) => {
        while (occGrid.length <= y) occGrid.push(new Array(cols).fill(null));
      };

      // Find max row
      let maxRow = 0;
      items.forEach(item => {
        const bottom = item.y + item.h;
        if (bottom > maxRow) maxRow = bottom;
      });
      for (let r = 0; r <= maxRow + 2; r++) ensureRow(r);

      // Fill occupancy
      items.forEach(item => {
        for (let dy = 0; dy < item.h; dy++) {
          for (let dx = 0; dx < item.w; dx++) {
            ensureRow(item.y + dy);
            occGrid[item.y + dy][item.x + dx] = item.i;
          }
        }
      });

      // Expand each widget rightward into empty space
      items.forEach(item => {
        let newW = item.w;
        while (item.x + newW < cols) {
          // Check if the column to the right is empty for the full height of this widget
          let canExpand = true;
          for (let dy = 0; dy < item.h; dy++) {
            ensureRow(item.y + dy);
            if (occGrid[item.y + dy][item.x + newW] !== null) {
              canExpand = false;
              break;
            }
          }
          if (!canExpand) break;
          // Claim those cells
          for (let dy = 0; dy < item.h; dy++) {
            occGrid[item.y + dy][item.x + newW] = item.i;
          }
          newW++;
        }
        item.w = newW;
        newLayoutMap[item.i].w = newW;
      });

      // Expand each widget downward into empty space (bounded by maxRow)
      items.forEach(item => {
        let newH = item.h;
        while (item.y + newH < maxRow) {
          const nextRow = item.y + newH;
          ensureRow(nextRow);
          // Check if the row below is empty for the full width of this widget
          let canExpand = true;
          for (let dx = 0; dx < item.w; dx++) {
            if (occGrid[nextRow][dx + item.x] !== null) {
              canExpand = false;
              break;
            }
          }
          if (!canExpand) break;
          // Claim those cells
          for (let dx = 0; dx < item.w; dx++) {
            occGrid[nextRow][dx + item.x] = item.i;
          }
          newH++;
        }
        item.h = newH;
        newLayoutMap[item.i].h = newH;
      });

      // ----- Trim trailing empty rows -----
      // Find actual max row after expansion
      let actualMaxRow = 0;
      items.forEach(item => {
        const bottom = item.y + item.h;
        if (bottom > actualMaxRow) actualMaxRow = bottom;
      });

      // ----- Update schema positions -----
      const updatedWidgets = prevSchema.widgets.map(widget => {
        const layout = newLayoutMap[widget.id];
        if (layout) {
          return {
            ...widget,
            position: {
              ...widget.position,
              column: layout.x + 1,
              row: layout.y + 1,
              col_span: layout.w,
              row_span: layout.h,
            },
          };
        }
        return widget;
      });

      queueMicrotask(() => setLayoutMap(newLayoutMap));

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
