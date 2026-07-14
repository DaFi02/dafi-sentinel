import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { ErrorBoundary } from "../components/ErrorBoundary";

function ThrowingComponent({ message }: { message: string }): JSX.Element {
  throw new Error(message);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ErrorBoundary", () => {
  it("renders children when no error is thrown", () => {
    render(
      <ErrorBoundary>
        <p>safe content</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("safe content")).toBeInTheDocument();
  });

  it("renders the fallback when a child throws", () => {
    // Suppress React's noisy error log for the thrown boundary.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <ThrowingComponent message="boom" />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    expect(spy).toHaveBeenCalled();
  });

  it("renders a retry button in the fallback", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <ThrowingComponent message="explode" />
      </ErrorBoundary>,
    );
    const retry = screen.getByRole("button", { name: /retry/i });
    expect(retry).toBeInTheDocument();
  });
});
