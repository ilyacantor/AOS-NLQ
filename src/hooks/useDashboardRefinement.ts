// *Last updated: 2026-02-07*

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  DashboardSchema,
  WidgetData,
} from '../types/generated-dashboard';
import { refreshLLMStats } from '../components/rag';

interface UseDashboardRefinementProps {
  schema: DashboardSchema | null;
  widgetData: Record<string, WidgetData>;
  setSchema: (schema: DashboardSchema | null) => void;
  setWidgetData: (data: Record<string, WidgetData>) => void;
  fetchWidgetData: (dashboard: DashboardSchema) => void;
  onRefinement?: (newSchema: DashboardSchema, widgetData?: Record<string, WidgetData>) => void;
  editMode: boolean;
  handleAutoArrange: () => void;
  dataMode?: 'live' | 'demo';
  sessionId?: string;
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
  dataMode = 'demo',
  sessionId,
}: UseDashboardRefinementProps): UseDashboardRefinementReturn {
  const [refinementQuery, setRefinementQuery] = useState('');
  const [isRefining, setIsRefining] = useState(false);
  const [refinementMessage, setRefinementMessage] = useState<string | null>(null);
  const refinementTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refineQueueRef = useRef<string[]>([]);
  const isRefiningRef = useRef(false);
  const schemaRef = useRef(schema);
  schemaRef.current = schema;
  const unmountedRef = useRef(false);

  useEffect(() => {
    unmountedRef.current = false;
    return () => {
      unmountedRef.current = true;
      if (refinementTimeoutRef.current) {
        clearTimeout(refinementTimeoutRef.current);
      }
    };
  }, []);

  const processRefinement = useCallback(async (query: string) => {
    if (unmountedRef.current) return;
    setIsRefining(true);
    isRefiningRef.current = true;
    setRefinementMessage(null);

    try {
      const currentSchema = schemaRef.current;
      if (!currentSchema) return;

      const response = await fetch('/api/v1/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: query,
          session_id: sessionId || currentSchema.id,
          data_mode: dataMode,
        }),
      });

      const data = await response.json();

      if (refinementTimeoutRef.current) {
        clearTimeout(refinementTimeoutRef.current);
        refinementTimeoutRef.current = null;
      }

      if (unmountedRef.current) return;

      if (data.response_type === 'dashboard' && data.dashboard) {
        const changesDescription = data.answer || null;

        const oldWidgetCount = currentSchema.widgets.length;
        const newWidgetCount = data.dashboard.widgets.length;

        setSchema(data.dashboard);

        const newWidgetData = data.dashboard_data && Object.keys(data.dashboard_data).length > 0
          ? data.dashboard_data
          : widgetData;

        if (data.dashboard_data && Object.keys(data.dashboard_data).length > 0) {
          setWidgetData(data.dashboard_data);
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
        } else if (changesDescription) {
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
      refreshLLMStats();
    }
  }, [onRefinement]);

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
    if (!schemaRef.current) return;

    refineQueueRef.current.push(query);

    if (!isRefiningRef.current) {
      processQueue();
    }
  }, [processQueue]);

  return {
    refinementQuery,
    setRefinementQuery,
    isRefining,
    refinementMessage,
    refineDashboard,
    processRefinement,
  };
}
