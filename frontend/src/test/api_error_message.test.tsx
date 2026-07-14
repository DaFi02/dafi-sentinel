import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ApiError, ChartValidationError, NetworkError } from "../api/client";
import { ApiErrorMessage } from "../components/ApiErrorMessage";

describe("ApiErrorMessage", () => {
  it("renders nothing when no error is provided", () => {
    const { container } = render(<ApiErrorMessage error={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the ApiError status and detail for an ApiError", () => {
    render(
      <ApiErrorMessage
        error={new ApiError(404, "evidence not found")}
        fallbackMessage="failed to load evidence"
      />,
    );
    expect(screen.getByText(/failed to load evidence/i)).toBeInTheDocument();
    expect(screen.getByText(/404/i)).toBeInTheDocument();
    expect(screen.getByText(/evidence not found/i)).toBeInTheDocument();
  });

  it("renders the generic message for a plain Error", () => {
    render(
      <ApiErrorMessage
        error={new Error("network blew up")}
        fallbackMessage="failed to load evidence"
      />,
    );
    expect(screen.getByText(/failed to load evidence/i)).toBeInTheDocument();
    expect(screen.getByText(/network blew up/i)).toBeInTheDocument();
  });

  it("renders a friendly message for a ChartValidationError", () => {
    render(
      <ApiErrorMessage
        error={new ChartValidationError("title", "title must be a non-empty string")}
        fallbackMessage="chart failed to render"
      />,
    );
    expect(screen.getByText(/chart failed to render/i)).toBeInTheDocument();
    expect(screen.getByText(/title must be a non-empty string/i)).toBeInTheDocument();
  });

  it("renders a network error message for NetworkError", () => {
    render(
      <ApiErrorMessage
        error={new NetworkError("connection refused")}
        fallbackMessage="failed to load evidence"
      />,
    );
    expect(screen.getByText(/network error/i)).toBeInTheDocument();
    expect(screen.getByText(/connection refused/i)).toBeInTheDocument();
  });
});
