import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";

// React logs the caught error itself; that noise is expected, not a failure.
beforeEach(() => vi.spyOn(console, "error").mockImplementation(() => {}));
afterEach(() => vi.restoreAllMocks());

const Boom = ({ bad }: { bad: boolean }) => {
  if (bad) throw new Error("ve_mV is not iterable");
  return <p>the panel</p>;
};

describe("ErrorBoundary", () => {
  it("passes children through when nothing is wrong", () => {
    render(
      <ErrorBoundary what="The field">
        <Boom bad={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("the panel")).toBeInTheDocument();
  });

  it("isolates a crash and names the panel, keeping the message visible", () => {
    render(
      <ErrorBoundary what="The field">
        <Boom bad />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("The field stopped")).toBeInTheDocument();
    expect(screen.getByText("ve_mV is not iterable")).toBeInTheDocument();
  });

  it("leaves the rest of the tree standing", () => {
    render(
      <div>
        <ErrorBoundary what="The 3D loupe">
          <Boom bad />
        </ErrorBoundary>
        <p>the controls</p>
      </div>,
    );
    expect(screen.getByText("The 3D loupe stopped")).toBeInTheDocument();
    expect(screen.getByText("the controls")).toBeInTheDocument(); // the point of all this
  });

  it("can be retried once the cause is gone", () => {
    const Host = () => {
      const [bad, setBad] = useState(true);
      return (
        <>
          <button onClick={() => setBad(false)}>fix it</button>
          <ErrorBoundary what="The field">
            <Boom bad={bad} />
          </ErrorBoundary>
        </>
      );
    };
    render(<Host />);
    expect(screen.getByText("The field stopped")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "fix it" }));
    fireEvent.click(screen.getByRole("button", { name: /Try again/ }));
    expect(screen.getByText("the panel")).toBeInTheDocument();
  });
});
