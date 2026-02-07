// *Last updated: 2026-02-07*

import { useState, useCallback } from 'react';
import { DashboardSchema, WidgetData } from '../types/generated-dashboard';
import { LayoutItem } from './useDashboardLayout';

// Storage keys
export const SAVED_DASHBOARDS_KEY = 'aos_saved_dashboards';
export const SAVED_TEMPLATES_KEY = 'aos_saved_templates';

export interface SavedDashboard {
  id: string;
  name: string;
  schema: DashboardSchema;
  savedAt: string;
  layoutMap?: Record<string, LayoutItem>;
  widgetData?: Record<string, WidgetData>;
}

export interface SavedTemplate {
  id: string;
  name: string;
  description: string;
  schema: DashboardSchema;
  savedAt: string;
}

export interface EvalResult {
  status: string;
  total: number;
  passed: number;
  failed: number;
  errors: number;
  skipped: number;
  duration_seconds: number;
  summary: string;
  failures: string[];
}

// =============================================================================
// Storage Helpers
// =============================================================================

export function getSavedDashboards(): SavedDashboard[] {
  try {
    const data = localStorage.getItem(SAVED_DASHBOARDS_KEY);
    return data ? JSON.parse(data) : [];
  } catch {
    return [];
  }
}

export function saveDashboard(dashboard: SavedDashboard): void {
  const dashboards = getSavedDashboards();
  const existing = dashboards.findIndex(d => d.id === dashboard.id);
  if (existing >= 0) {
    dashboards[existing] = dashboard;
  } else {
    dashboards.push(dashboard);
  }
  localStorage.setItem(SAVED_DASHBOARDS_KEY, JSON.stringify(dashboards));
}

export function deleteSavedDashboard(id: string): void {
  const dashboards = getSavedDashboards().filter(d => d.id !== id);
  localStorage.setItem(SAVED_DASHBOARDS_KEY, JSON.stringify(dashboards));
}

export function getSavedTemplates(): SavedTemplate[] {
  try {
    const data = localStorage.getItem(SAVED_TEMPLATES_KEY);
    return data ? JSON.parse(data) : [];
  } catch {
    return [];
  }
}

export function saveTemplate(template: SavedTemplate): void {
  const templates = getSavedTemplates();
  templates.push(template);
  localStorage.setItem(SAVED_TEMPLATES_KEY, JSON.stringify(templates));
}

export function deleteSavedTemplate(id: string): void {
  const templates = getSavedTemplates().filter(t => t.id !== id);
  localStorage.setItem(SAVED_TEMPLATES_KEY, JSON.stringify(templates));
}

// =============================================================================
// Hook
// =============================================================================

export interface UseDashboardPersistenceProps {
  schema: DashboardSchema | null;
  layoutMap: Record<string, any>;
  widgetData: Record<string, any>;
  setSchema: (schema: DashboardSchema | null) => void;
  setLayoutMap: (map: Record<string, any>) => void;
  setWidgetData: (data: Record<string, any>) => void;
  fetchWidgetData: (schema: DashboardSchema) => void;
}

export function useDashboardPersistence({
  schema,
  layoutMap,
  widgetData,
  setSchema,
  setLayoutMap,
  setWidgetData,
  fetchWidgetData,
}: UseDashboardPersistenceProps) {
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [showLoadModal, setShowLoadModal] = useState(false);
  const [showTestModal, setShowTestModal] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [templateName, setTemplateName] = useState('');
  const [templateDesc, setTemplateDesc] = useState('');
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [testRunning, setTestRunning] = useState(false);
  const [testResult, setTestResult] = useState<EvalResult | null>(null);

  const handleRunTests = useCallback(async () => {
    setTestRunning(true);
    setTestResult(null);
    setShowTestModal(true);
    try {
      const response = await fetch('/api/v1/eval/run', { method: 'POST' });
      const result = await response.json();
      setTestResult(result);
    } catch (err) {
      setTestResult({
        status: 'error',
        total: 0,
        passed: 0,
        failed: 0,
        errors: 1,
        skipped: 0,
        duration_seconds: 0,
        summary: `Failed to run tests: ${err}`,
        failures: [String(err)],
      });
    } finally {
      setTestRunning(false);
    }
  }, []);

  const handleSave = useCallback(() => {
    if (!schema || !saveName.trim()) return;

    const saved: SavedDashboard = {
      id: schema.id,
      name: saveName.trim(),
      schema: schema,
      savedAt: new Date().toISOString(),
      layoutMap: layoutMap,
      widgetData: widgetData,
    };
    saveDashboard(saved);
    setShowSaveModal(false);
    setSaveName('');
    setSaveSuccess('Dashboard saved!');
    setTimeout(() => setSaveSuccess(null), 2000);
  }, [schema, saveName, layoutMap, widgetData]);

  const handleSaveAsTemplate = useCallback(() => {
    if (!schema || !templateName.trim()) return;

    const template: SavedTemplate = {
      id: `template_${Date.now()}`,
      name: templateName.trim(),
      description: templateDesc.trim(),
      schema: {
        ...schema,
        id: `template_${Date.now()}`,
        source_query: '',
        refinement_history: [],
      },
      savedAt: new Date().toISOString(),
    };
    saveTemplate(template);
    setShowTemplateModal(false);
    setTemplateName('');
    setTemplateDesc('');
    setSaveSuccess('Template saved!');
    setTimeout(() => setSaveSuccess(null), 2000);
  }, [schema, templateName, templateDesc]);

  const handleLoad = useCallback((item: SavedDashboard | SavedTemplate) => {
    setSchema(item.schema);

    const savedDashboard = item as SavedDashboard;
    if (savedDashboard.layoutMap && Object.keys(savedDashboard.layoutMap).length > 0) {
      setLayoutMap(savedDashboard.layoutMap);
    } else {
      setLayoutMap({});
    }

    if (savedDashboard.widgetData && Object.keys(savedDashboard.widgetData).length > 0) {
      setWidgetData(savedDashboard.widgetData);
    } else {
      fetchWidgetData(item.schema);
    }

    setShowLoadModal(false);
  }, [setSchema, setLayoutMap, setWidgetData, fetchWidgetData]);

  return {
    showSaveModal,
    setShowSaveModal,
    showTemplateModal,
    setShowTemplateModal,
    showLoadModal,
    setShowLoadModal,
    showTestModal,
    setShowTestModal,
    saveName,
    setSaveName,
    templateName,
    setTemplateName,
    templateDesc,
    setTemplateDesc,
    saveSuccess,
    setSaveSuccess,
    testRunning,
    setTestRunning,
    testResult,
    setTestResult,
    handleSave,
    handleSaveAsTemplate,
    handleLoad,
    handleRunTests,
  };
}
