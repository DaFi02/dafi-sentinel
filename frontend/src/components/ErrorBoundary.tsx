import { Component, ErrorInfo, ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Top-level error boundary for the DAFI Sentinel dashboard.
 *
 * R4 crit#4: a single broken panel used to take down the whole
 * React tree. The boundary catches any render-phase exception in
 * the subtree, logs the error to the console, and surfaces a
 * fallback with a retry button so the user can recover without a
 * full page reload.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Log to the console so dev tools (and CI logs) surface the
    // failure. The dashboard does not have a remote reporter wired
    // in; the log is the operator's signal.
    // eslint-disable-next-line no-console
    console.error("DAFI Sentinel error boundary caught:", error, info.componentStack);
  }

  private reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    const { children, fallback } = this.props;
    if (error === null) {
      return children;
    }
    if (fallback) {
      return fallback(error, this.reset);
    }
    return (
      <div role="alert" className="error-boundary">
        <h2>Something went wrong.</h2>
        <p className="muted">{error.message}</p>
        <button type="button" className="button" onClick={this.reset}>
          retry
        </button>
      </div>
    );
  }
}
