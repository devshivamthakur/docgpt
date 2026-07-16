import { Component, type ReactNode, type ErrorInfo } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Catches render errors in its subtree and displays a fallback UI
 * instead of crashing the whole app.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Error boundary caught:', error, info);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-4 text-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-500/10">
            <span className="text-3xl">⚠️</span>
          </div>
          <h2 className="mb-2 text-xl font-semibold text-white">Something went wrong</h2>
          <p className="mb-6 max-w-md text-sm text-slate-400">
            An unexpected error occurred. Please try signing in again.
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null });
              window.location.href = '/login';
            }}
            className="rounded-full bg-gradient-to-r from-cyan-500 to-violet-500 px-6 py-2 text-sm font-medium text-white shadow-lg transition hover:opacity-90"
          >
            Go to Login
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
