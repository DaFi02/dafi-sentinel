import { ApiError, ChartValidationError, NetworkError } from "../api/client";

/**
 * Shared error display for the dashboard.
 *
 * R2 high#5: the prior surface duplicated an `if (error instanceof
 * ApiError) { ... } else if (error instanceof Error) { ... }` block
 * across every page. Each block rendered a slightly different
 * string, and a new error class (e.g., ``ChartValidationError``)
 * silently rendered the wrong message. The shared component pins
 * one rendering rule per error class and one fallback string the
 * caller can localize.
 */

interface ApiErrorMessageProps {
  error: Error | null;
  fallbackMessage?: string;
}

export function ApiErrorMessage({ error, fallbackMessage }: ApiErrorMessageProps): JSX.Element | null {
  if (error === null) {
    return null;
  }
  if (error instanceof ApiError) {
    return (
      <p className="error" role="alert">
        {fallbackMessage ?? "request failed"}
        {": "}
        <span className="muted">
          ({error.status} {error.detail})
        </span>
      </p>
    );
  }
  if (error instanceof ChartValidationError) {
    return (
      <p className="error" role="alert">
        {fallbackMessage ?? "chart failed to render"}
        {": "}
        <span className="muted">{error.message}</span>
      </p>
    );
  }
  if (error instanceof NetworkError) {
    return (
      <p className="error" role="alert">
        network error
        {": "}
        <span className="muted">{error.message}</span>
      </p>
    );
  }
  return (
    <p className="error" role="alert">
      {fallbackMessage ?? "request failed"}
      {": "}
      <span className="muted">{error.message}</span>
    </p>
  );
}
