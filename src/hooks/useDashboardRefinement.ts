// *Last updated: 2026-02-07*

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  DashboardSchema,
  WidgetData,
  DashboardRefinementResponse,
} from '../types/generated-dashboard';

interface UseDashboardRefinementProps {
  schema: DashboardSchema | null;
  widgetData: Record<string, WidgetData>;
  setSchema: (schema: DashboardSchema | null) => void;
  setWidgetData: (data: Record<string, WidgetData>) => void;
  fetchWidgetData: (dashboard: DashboardSchema) => void;
  onRefinement?: (newSchema: DashboardSchema, widgetData?: Record<string, WidgetData>) => void;
  editMode: boolean;
  handleAutoArrange: () => void;
}

interface UseDashboardRefinementReturn {
  refinementQuery: string;
  setRefinementQuery: (q: string) => void;
  isRefining: boolean;
  refinementMessage: string | null;
  refineDashboard: (query: string) => void;
  processRefinement: (query: string) => Promise<void>;
}

export function useDashboardRefinement({
  schema,
  widgetData,
  setSchema,
  setWidgetData,
  fetchWidgetData,
  onRefinement,
  editMode,
  handleAutoArrange,
}: UseDashboardRefinementProps): UseDashboardRefinementReturn {
  const [refinementQuery, setRefinementQuery] = useState('');
  const [isRefining, setIsRefining] = useState(false);
  const [refinementMessage, setRefinementMessage] = useState<string | null>(null);
  const refinementTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refineQueueRef = useRef<string[]>([]);
  const isRefiningRef = useRef(false);

  useEffect(() => {
    return () => {
      if (refinementTimeoutRef.current) {
        clearTimeout(refinementTimeoutRef.current);
      }
    };
  }, []);

  const processRefinement = useCallback(async (query: string) => {
    setIsRefining(true);
    isRefiningRef.current = true;
    setRefinementMessage(null);

    try {
      const currentSchema = schema;
      if (!currentSchema) return;

      const response = await fetch('/api/v1/dashboard/refine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dashboard_id: currentSchema.id,
          refinement_query: query,
        }),
      });

      const data: DashboardRefinementResponse = await response.json();

      if (refinementTimeoutRef.current) {
        clearTimeout(refinementTimeoutRef.current);
        refinementTimeoutRef.current = null;
      }

      if (data.refinement_status === 'noop') {
        setRefinementMessage(null);
      } else if (data.success && data.dashboard) {
        const changesDescription = data.changes_made && data.changes_made.length > 0
          ? data.changes_made.join(', ')
          : null;

        const oldWidgetCount = currentSchema.widgets.length;
        const newWidgetCount = data.dashboard.widgets.length;

        setSchema(data.dashboard);

        const newWidgetData = data.widget_data && Object.keys(data.widget_data).length > 0
          ? data.widget_data
          : widgetData;

        if (data.widget_data && Object.keys(data.widget_data).length > 0) {
          setWidgetData(data.widget_data);
        } else {
          fetchWidgetData(data.dashboard);
        }

        onRefinement?.(data.dashboard, newWidgetData);

        const widgetsAdded = newWidgetCount > oldWidgetCount;
        const widgetsRemoved = newWidgetCount < oldWidgetCount;

        if (widgetsAdded) {
          const added = newWidgetCount - oldWidgetCount;
          setRefinementMessage(`Added ${added} widget${added > 1 ? 's' : ''} to dashboard`);
        } else if (widgetsRemoved) {
          const removed = oldWidgetCount - newWidgetCount;
          setRefinementMessage(`Removed ${removed} widget${removed > 1 ? 's' : ''} from dashboard`);
        } else if (changesDescription && !changesDescription.includes('Applied refinement:')) {
          setRefinementMessage(changesDescription);
        } else {
          setRefinementMessage('Dashboard updated');
        }

        refinementTimeoutRef.current = setTimeout(() => setRefinementMessage(null), 4000);
      } else {
        setRefinementMessage(null);
      }
    } catch (err) {
      console.warn('Dashboard refinement error:', err);
      setRefinementMessage('Could not apply that refinement');
      refinementTimeoutRef.current = setTimeout(() => setRefinementMessage(null), 4000);
    } finally {
      setIsRefining(false);
      isRefiningRef.current = false;
      setRefinementQuery('');
    }
  }, [schema, onRefinement]);

  const processQueue = useCallback(async () => {
    while (refineQueueRef.current.length > 0) {
      const nextQuery = refineQueueRef.current.shift()!;
      await processRefinement(nextQuery);
      await new Promise(r => setTimeout(r, 100));
    }
    if (!editMode) {
      handleAutoArrange();
    }
  }, [processRefinement, editMode, handleAutoArrange]);

  const refineDashboard = useCallback(async (query: string) => {
    if (!schema) return;

    refineQueueRef.current.push(query);

    if (!isRefiningRef.current) {
      processQueue();
    }
  }, [schema, processQueue]);

  return {
    refinementQuery,
    setRefinementQuery,
    isRefining,
    refinementMessage,
    refineDashboard,
    processRefinement,
  };
}
