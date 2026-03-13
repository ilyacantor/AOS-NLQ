import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  errorMessage: string | null;
}

export class DashboardErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, errorMessage: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, errorMessage: error.message };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('[Dashboard] Rendering error caught by boundary:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, errorMessage: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="text-center max-w-md">
            <div className="text-4xl mb-4">⚠</div>
            <h3 className="text-lg font-semibold text-white mb-2">
              Dashboard encountered an issue
            </h3>
            <p className="text-slate-400 text-sm mb-6">
              Something went wrong while rendering the dashboard. This can happen during rapid interactions.
            </p>
            <button
              onClick={this.handleReset}
              className="px-5 py-2.5 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 transition-colors text-sm font-medium"
            >
              Reload Dashboard
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
