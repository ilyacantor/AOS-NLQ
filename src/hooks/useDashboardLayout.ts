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
    setLayoutMap(prevMap => {
      const newMap: Record<string, LayoutItem> = { ...prevMap };
      newLayout.forEach(item => {
        newMap[item.i] = item;
      });
      return newMap;
    });

    setSchema(prevSchema => {
      if (!prevSchema) return prevSchema;
      const updatedWidgets = prevSchema.widgets.map(widget => {
        const layoutItem = newLayout.find(l => l.i === widget.id);
        if (layoutItem) {
          return {
            ...widget,
            position: {
              ...widget.position,
              column: layoutItem.x + 1,
              row: layoutItem.y + 1,
              col_span: layoutItem.w,
              row_span: layoutItem.h,
            },
          };
        }
        return widget;
      });
      return { ...prevSchema, widgets: updatedWidgets };
    });
  }, []);

  const handleAutoArrange = useCallback(() => {
    setSchema(prevSchema => {
      if (!prevSchema) return prevSchema;

      const cols = prevSchema.layout.columns;

      const kpis = prevSchema.widgets.filter(w => w.type === 'kpi_card');
      const charts = prevSchema.widgets.filter(w =>
        ['line_chart', 'bar_chart', 'area_chart', 'stacked_bar', 'donut_chart', 'horizontal_bar'].includes(w.type)
      );
      const tables = prevSchema.widgets.filter(w => w.type === 'data_table');
      const others = prevSchema.widgets.filter(w =>
        !['kpi_card', 'line_chart', 'bar_chart', 'area_chart', 'stacked_bar', 'donut_chart', 'horizontal_bar', 'data_table'].includes(w.type)
      );

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

      const place = (x: number, y: number, w: number, h: number) => {
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

      kpis.forEach(widget => {
        const w = Math.min(widget.position.col_span || 3, cols);
        const h = widget.position.row_span || 2;
        const pos = findPosition(w, h);
        place(pos.x, pos.y, w, h);
        newLayoutMap[widget.id] = { i: widget.id, x: pos.x, y: pos.y, w, h, minW: 2, minH: 2 };
      });

      charts.forEach(widget => {
        const w = Math.min(widget.position.col_span || 6, cols);
        const h = widget.position.row_span || 3;
        const pos = findPosition(w, h);
        place(pos.x, pos.y, w, h);
        newLayoutMap[widget.id] = { i: widget.id, x: pos.x, y: pos.y, w, h, minW: 2, minH: 2 };
      });

      tables.forEach(widget => {
        const w = Math.min(widget.position.col_span || 4, cols);
        const h = widget.position.row_span || 3;
        const pos = findPosition(w, h);
        place(pos.x, pos.y, w, h);
        newLayoutMap[widget.id] = { i: widget.id, x: pos.x, y: pos.y, w, h, minW: 2, minH: 2 };
      });

      others.forEach(widget => {
        const w = Math.min(widget.position.col_span || 3, cols);
        const h = widget.position.row_span || 2;
        const pos = findPosition(w, h);
        place(pos.x, pos.y, w, h);
        newLayoutMap[widget.id] = { i: widget.id, x: pos.x, y: pos.y, w, h, minW: 2, minH: 2 };
      });

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
