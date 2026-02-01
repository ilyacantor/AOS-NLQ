import { useReducer, useCallback } from 'react';
import { IntentMapResponse } from '../components/galaxy';
import { DashboardSchema } from '../components/generated-dashboard';

/**
 * Query history item structure
 */
export interface QueryHistoryItem {
  id: string;
  query: string;
  timestamp: string;
  duration: string;
  tag: string;
  count: number;
}

/**
 * View modes for the application
 */
export type ViewMode = 'galaxy' | 'dashboard' | 'guide';

/**
 * Persona options
 */
export type Persona = 'CFO' | 'CRO' | 'COO' | 'CTO' | 'CHRO';

/**
 * Panel tabs in the sidebar
 */
export type PanelTab = 'History' | 'Learning' | 'Data Gaps';

/**
 * Query mode (static data vs AI)
 */
export type QueryMode = 'static' | 'ai';

/**
 * Complete application state
 */
export interface AppState {
  // Query input state
  query: string;

  // View and navigation state
  viewMode: ViewMode;
  selectedPersona: Persona;
  panelTab: PanelTab;
  sidebarOpen: boolean;
  mobileMenuOpen: boolean;

  // Query processing state
  queryMode: QueryMode;
  queryHistory: QueryHistoryItem[];
  isLoading: boolean;
  lastDuration: string;

  // Galaxy view state
  galaxyResponse: IntentMapResponse | null;

  // Dashboard state
  dashboardSchema: DashboardSchema | null;
  dashboardWidgetData: Record<string, any>;
  isGeneratingDashboard: boolean;
  dashboardError: string | null;

  // Initialization flags
  hasLoadedDefault: boolean;
  hasLoadedDefaultDashboard: boolean;
}

/**
 * Initial application state
 */
export const initialAppState: AppState = {
  query: '',
  viewMode: 'galaxy',
  selectedPersona: 'CFO',
  panelTab: 'History',
  sidebarOpen: false,
  mobileMenuOpen: false,
  queryMode: 'ai',
  queryHistory: [],
  isLoading: false,
  lastDuration: '',
  galaxyResponse: null,
  dashboardSchema: null,
  dashboardWidgetData: {},
  isGeneratingDashboard: false,
  dashboardError: null,
  hasLoadedDefault: false,
  hasLoadedDefaultDashboard: false,
};

/**
 * Action types for the reducer
 */
export type AppAction =
  // Query input actions
  | { type: 'SET_QUERY'; payload: string }
  | { type: 'CLEAR_QUERY' }

  // View and navigation actions
  | { type: 'SET_VIEW_MODE'; payload: ViewMode }
  | { type: 'SET_PERSONA'; payload: Persona }
  | { type: 'SET_PANEL_TAB'; payload: PanelTab }
  | { type: 'SET_SIDEBAR_OPEN'; payload: boolean }
  | { type: 'SET_MOBILE_MENU_OPEN'; payload: boolean }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'TOGGLE_MOBILE_MENU' }

  // Query processing actions
  | { type: 'SET_QUERY_MODE'; payload: QueryMode }
  | { type: 'SET_QUERY_HISTORY'; payload: QueryHistoryItem[] }
  | { type: 'ADD_HISTORY_ITEM'; payload: QueryHistoryItem }
  | { type: 'START_LOADING' }
  | { type: 'STOP_LOADING' }
  | { type: 'SET_LAST_DURATION'; payload: string }

  // Galaxy view actions
  | { type: 'SET_GALAXY_RESPONSE'; payload: IntentMapResponse | null }
  | {
      type: 'GALAXY_QUERY_SUCCESS';
      payload: { response: IntentMapResponse; duration: string; historyItem: QueryHistoryItem };
    }
  | { type: 'GALAXY_QUERY_ERROR'; payload: IntentMapResponse }

  // Dashboard actions
  | { type: 'SET_DASHBOARD_SCHEMA'; payload: DashboardSchema | null }
  | { type: 'SET_DASHBOARD_WIDGET_DATA'; payload: Record<string, any> }
  | { type: 'START_GENERATING_DASHBOARD' }
  | { type: 'STOP_GENERATING_DASHBOARD' }
  | { type: 'SET_DASHBOARD_ERROR'; payload: string | null }
  | {
      type: 'DASHBOARD_GENERATION_SUCCESS';
      payload: { schema: DashboardSchema; widgetData: Record<string, any> };
    }
  | { type: 'DASHBOARD_GENERATION_ERROR'; payload: string }
  | { type: 'CLEAR_DASHBOARD' }

  // Initialization actions
  | { type: 'MARK_DEFAULT_LOADED' }
  | { type: 'MARK_DEFAULT_DASHBOARD_LOADED' }

  // Batch actions for common workflows
  | { type: 'START_GALAXY_QUERY' }
  | { type: 'SWITCH_TO_DASHBOARD_WITH_HISTORY'; payload: QueryHistoryItem };

/**
 * Aggregate history items by query text
 */
export function aggregateHistory(items: QueryHistoryItem[]): QueryHistoryItem[] {
  const queryMap = new Map<string, QueryHistoryItem>();
  for (const item of items) {
    const normalizedQuery = item.query.toLowerCase().trim();
    const existing = queryMap.get(normalizedQuery);
    if (existing) {
      existing.count += 1;
    } else {
      queryMap.set(normalizedQuery, { ...item, count: 1 });
    }
  }
  return Array.from(queryMap.values());
}

/**
 * Application state reducer
 */
export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    // Query input actions
    case 'SET_QUERY':
      return { ...state, query: action.payload };
    case 'CLEAR_QUERY':
      return { ...state, query: '' };

    // View and navigation actions
    case 'SET_VIEW_MODE':
      return { ...state, viewMode: action.payload };
    case 'SET_PERSONA':
      return { ...state, selectedPersona: action.payload };
    case 'SET_PANEL_TAB':
      return { ...state, panelTab: action.payload };
    case 'SET_SIDEBAR_OPEN':
      return { ...state, sidebarOpen: action.payload };
    case 'SET_MOBILE_MENU_OPEN':
      return { ...state, mobileMenuOpen: action.payload };
    case 'TOGGLE_SIDEBAR':
      return { ...state, sidebarOpen: !state.sidebarOpen };
    case 'TOGGLE_MOBILE_MENU':
      return { ...state, mobileMenuOpen: !state.mobileMenuOpen };

    // Query processing actions
    case 'SET_QUERY_MODE':
      return { ...state, queryMode: action.payload };
    case 'SET_QUERY_HISTORY':
      return { ...state, queryHistory: action.payload };
    case 'ADD_HISTORY_ITEM':
      return {
        ...state,
        queryHistory: aggregateHistory([action.payload, ...state.queryHistory]),
      };
    case 'START_LOADING':
      return { ...state, isLoading: true };
    case 'STOP_LOADING':
      return { ...state, isLoading: false };
    case 'SET_LAST_DURATION':
      return { ...state, lastDuration: action.payload };

    // Galaxy view actions
    case 'SET_GALAXY_RESPONSE':
      return { ...state, galaxyResponse: action.payload };
    case 'GALAXY_QUERY_SUCCESS':
      return {
        ...state,
        galaxyResponse: action.payload.response,
        lastDuration: action.payload.duration,
        queryHistory: aggregateHistory([action.payload.historyItem, ...state.queryHistory]),
        isLoading: false,
      };
    case 'GALAXY_QUERY_ERROR':
      return {
        ...state,
        galaxyResponse: action.payload,
        isLoading: false,
      };

    // Dashboard actions
    case 'SET_DASHBOARD_SCHEMA':
      return { ...state, dashboardSchema: action.payload };
    case 'SET_DASHBOARD_WIDGET_DATA':
      return { ...state, dashboardWidgetData: action.payload };
    case 'START_GENERATING_DASHBOARD':
      return { ...state, isGeneratingDashboard: true, dashboardError: null };
    case 'STOP_GENERATING_DASHBOARD':
      return { ...state, isGeneratingDashboard: false };
    case 'SET_DASHBOARD_ERROR':
      return { ...state, dashboardError: action.payload };
    case 'DASHBOARD_GENERATION_SUCCESS':
      return {
        ...state,
        dashboardSchema: action.payload.schema,
        dashboardWidgetData: action.payload.widgetData,
        isGeneratingDashboard: false,
        dashboardError: null,
      };
    case 'DASHBOARD_GENERATION_ERROR':
      return {
        ...state,
        dashboardError: action.payload,
        isGeneratingDashboard: false,
      };
    case 'CLEAR_DASHBOARD':
      return {
        ...state,
        dashboardSchema: null,
        dashboardWidgetData: {},
        dashboardError: null,
      };

    // Initialization actions
    case 'MARK_DEFAULT_LOADED':
      return { ...state, hasLoadedDefault: true };
    case 'MARK_DEFAULT_DASHBOARD_LOADED':
      return { ...state, hasLoadedDefaultDashboard: true };

    // Batch actions for common workflows
    case 'START_GALAXY_QUERY':
      return {
        ...state,
        isLoading: true,
        query: '',
        galaxyResponse: null,
      };
    case 'SWITCH_TO_DASHBOARD_WITH_HISTORY':
      return {
        ...state,
        viewMode: 'dashboard',
        query: '',
        queryHistory: aggregateHistory([action.payload, ...state.queryHistory]),
      };

    default:
      return state;
  }
}

/**
 * Custom hook for application state management
 */
export function useAppState() {
  const [state, dispatch] = useReducer(appReducer, initialAppState);

  // Convenience action creators
  const actions = {
    setQuery: useCallback((query: string) => dispatch({ type: 'SET_QUERY', payload: query }), []),
    clearQuery: useCallback(() => dispatch({ type: 'CLEAR_QUERY' }), []),
    setViewMode: useCallback(
      (mode: ViewMode) => dispatch({ type: 'SET_VIEW_MODE', payload: mode }),
      []
    ),
    setPersona: useCallback(
      (persona: Persona) => dispatch({ type: 'SET_PERSONA', payload: persona }),
      []
    ),
    setPanelTab: useCallback(
      (tab: PanelTab) => dispatch({ type: 'SET_PANEL_TAB', payload: tab }),
      []
    ),
    setSidebarOpen: useCallback(
      (open: boolean) => dispatch({ type: 'SET_SIDEBAR_OPEN', payload: open }),
      []
    ),
    setMobileMenuOpen: useCallback(
      (open: boolean) => dispatch({ type: 'SET_MOBILE_MENU_OPEN', payload: open }),
      []
    ),
    toggleSidebar: useCallback(() => dispatch({ type: 'TOGGLE_SIDEBAR' }), []),
    toggleMobileMenu: useCallback(() => dispatch({ type: 'TOGGLE_MOBILE_MENU' }), []),
    setQueryMode: useCallback(
      (mode: QueryMode) => dispatch({ type: 'SET_QUERY_MODE', payload: mode }),
      []
    ),
    setQueryHistory: useCallback(
      (history: QueryHistoryItem[]) => dispatch({ type: 'SET_QUERY_HISTORY', payload: history }),
      []
    ),
    addHistoryItem: useCallback(
      (item: QueryHistoryItem) => dispatch({ type: 'ADD_HISTORY_ITEM', payload: item }),
      []
    ),
    startLoading: useCallback(() => dispatch({ type: 'START_LOADING' }), []),
    stopLoading: useCallback(() => dispatch({ type: 'STOP_LOADING' }), []),
    setLastDuration: useCallback(
      (duration: string) => dispatch({ type: 'SET_LAST_DURATION', payload: duration }),
      []
    ),
    setGalaxyResponse: useCallback(
      (response: IntentMapResponse | null) =>
        dispatch({ type: 'SET_GALAXY_RESPONSE', payload: response }),
      []
    ),
    galaxyQuerySuccess: useCallback(
      (response: IntentMapResponse, duration: string, historyItem: QueryHistoryItem) =>
        dispatch({ type: 'GALAXY_QUERY_SUCCESS', payload: { response, duration, historyItem } }),
      []
    ),
    galaxyQueryError: useCallback(
      (response: IntentMapResponse) => dispatch({ type: 'GALAXY_QUERY_ERROR', payload: response }),
      []
    ),
    setDashboardSchema: useCallback(
      (schema: DashboardSchema | null) =>
        dispatch({ type: 'SET_DASHBOARD_SCHEMA', payload: schema }),
      []
    ),
    setDashboardWidgetData: useCallback(
      (data: Record<string, any>) => dispatch({ type: 'SET_DASHBOARD_WIDGET_DATA', payload: data }),
      []
    ),
    startGeneratingDashboard: useCallback(
      () => dispatch({ type: 'START_GENERATING_DASHBOARD' }),
      []
    ),
    stopGeneratingDashboard: useCallback(
      () => dispatch({ type: 'STOP_GENERATING_DASHBOARD' }),
      []
    ),
    setDashboardError: useCallback(
      (error: string | null) => dispatch({ type: 'SET_DASHBOARD_ERROR', payload: error }),
      []
    ),
    dashboardGenerationSuccess: useCallback(
      (schema: DashboardSchema, widgetData: Record<string, any>) =>
        dispatch({ type: 'DASHBOARD_GENERATION_SUCCESS', payload: { schema, widgetData } }),
      []
    ),
    dashboardGenerationError: useCallback(
      (error: string) => dispatch({ type: 'DASHBOARD_GENERATION_ERROR', payload: error }),
      []
    ),
    clearDashboard: useCallback(() => dispatch({ type: 'CLEAR_DASHBOARD' }), []),
    markDefaultLoaded: useCallback(() => dispatch({ type: 'MARK_DEFAULT_LOADED' }), []),
    markDefaultDashboardLoaded: useCallback(
      () => dispatch({ type: 'MARK_DEFAULT_DASHBOARD_LOADED' }),
      []
    ),
    startGalaxyQuery: useCallback(() => dispatch({ type: 'START_GALAXY_QUERY' }), []),
    switchToDashboardWithHistory: useCallback(
      (item: QueryHistoryItem) =>
        dispatch({ type: 'SWITCH_TO_DASHBOARD_WITH_HISTORY', payload: item }),
      []
    ),
  };

  return { state, dispatch, actions };
}

export default useAppState;
