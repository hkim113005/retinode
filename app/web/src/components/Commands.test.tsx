import { fireEvent, render, screen } from "@testing-library/react";
import { useMemo } from "react";
import { describe, expect, it, vi } from "vitest";
import { CommandProvider, useCommands } from "./Commands";

const open = () => fireEvent.keyDown(window, { key: "k", metaKey: true });

function Screen({ run, label = "Run the sweep" }: { run: () => void; label?: string }) {
  useCommands(
    "screen",
    useMemo(
      () => [
        { id: "run", group: "Study", label, run },
        { id: "off", group: "Study", label: "Already running", disabled: true, run: vi.fn() },
      ],
      [run, label],
    ),
  );
  return <p>the screen</p>;
}

const app = (run = vi.fn()) => {
  render(
    <CommandProvider>
      <Screen run={run} />
    </CommandProvider>,
  );
  return run;
};

describe("the command palette", () => {
  it("opens on ⌘K and closes on Escape", () => {
    app();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    open();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens on Ctrl-K too, for anyone not on a Mac", () => {
    app();
    fireEvent.keyDown(window, { key: "K", ctrlKey: true }); // capital: shift may be held
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("lists what the mounted screen registered, and runs it on Enter", () => {
    const run = app();
    open();
    expect(screen.getByRole("option", { name: /Run the sweep/ })).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter" });
    expect(run).toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); // and it closes
  });

  it("filters as you type, and says so when nothing matches", () => {
    app();
    open();
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "sweep" } });
    expect(screen.getAllByRole("option")).toHaveLength(1);
    fireEvent.change(input, { target: { value: "zzz" } });
    expect(screen.queryAllByRole("option")).toHaveLength(0);
    expect(screen.getByText(/No command matches/)).toBeInTheDocument();
  });

  it("moves the selection with the arrows, wrapping at the ends", () => {
    app();
    open();
    const input = screen.getByRole("combobox");
    const sel = () => screen.getAllByRole("option").findIndex((o) => o.getAttribute("aria-selected") === "true");
    expect(sel()).toBe(0);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(sel()).toBe(1);
    fireEvent.keyDown(input, { key: "ArrowDown" }); // wraps rather than dead-ending
    expect(sel()).toBe(0);
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(sel()).toBe(1);
  });

  it("will not run a disabled command", () => {
    const run = vi.fn();
    render(
      <CommandProvider>
        <Screen run={run} />
      </CommandProvider>,
    );
    open();
    fireEvent.click(screen.getByRole("option", { name: /Already running/ }));
    expect(run).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument(); // stays open, nothing happened
  });

  it("drops a screen's commands when it unmounts", () => {
    const { unmount, rerender } = render(
      <CommandProvider>
        <Screen run={vi.fn()} />
      </CommandProvider>,
    );
    open();
    expect(screen.getByRole("option", { name: /Run the sweep/ })).toBeInTheDocument();
    rerender(<CommandProvider />);
    expect(screen.queryByRole("option", { name: /Run the sweep/ })).not.toBeInTheDocument();
    unmount();
  });
});
