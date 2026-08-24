// The command palette (⌘K / Ctrl-K). It is what makes the design doc's "every action
// is reachable by keyboard" true (docs/phase-7-design.md). Screens register their own
// actions rather than App knowing about all of them, so a screen's commands live next
// to the code that performs them and disappear when that screen unmounts.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

export type Command = {
  id: string;
  label: string;
  group: string;
  hint?: string; // the right-hand grey note: shortcut, state, or consequence
  disabled?: boolean;
  run: () => void;
};

type Registry = { set: (owner: string, cmds: Command[]) => void };
const Ctx = createContext<Registry | null>(null);

/**
 * Register `cmds` under `owner` for as long as the caller is mounted. MEMOISE the
 * array (useMemo), because a fresh array each render would re-register forever.
 */
export function useCommands(owner: string, cmds: Command[]): void {
  const reg = useContext(Ctx);
  useEffect(() => {
    reg?.set(owner, cmds);
    return () => reg?.set(owner, []);
  }, [reg, owner, cmds]);
}

const match = (c: Command, q: string) =>
  !q || `${c.group} ${c.label} ${c.hint ?? ""}`.toLowerCase().includes(q.toLowerCase());

export function CommandProvider({ children }: { children?: React.ReactNode }) {
  const [owners, setOwners] = useState<Record<string, Command[]>>({});
  const [open, setOpen] = useState(false);

  const set = useCallback((owner: string, cmds: Command[]) => {
    setOwners((m) => ({ ...m, [owner]: cmds }));
  }, []);
  const registry = useMemo(() => ({ set }), [set]);
  const commands = useMemo(() => Object.values(owners).flat(), [owners]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <Ctx.Provider value={registry}>
      {children}
      {open && <Palette commands={commands} onClose={() => setOpen(false)} />}
      <button className="cmdhint" onClick={() => setOpen(true)} aria-label="Open the command palette">
        <kbd>⌘K</kbd> commands
      </button>
    </Ctx.Provider>
  );
}

function Palette({ commands, onClose }: { commands: Command[]; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const hits = useMemo(() => commands.filter((c) => match(c, q)), [commands, q]);

  useEffect(() => input.current?.focus(), []);
  useEffect(() => setI(0), [q]);

  const run = (c: Command | undefined) => {
    if (!c || c.disabled) return;
    onClose();
    c.run();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") return onClose();
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!hits.length) return;
      const d = e.key === "ArrowDown" ? 1 : -1;
      setI((v) => (v + d + hits.length) % hits.length); // wraps, so the list has no dead end
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      run(hits[i]);
    }
  };

  return (
    // biome-ignore lint/a11y/useKeyWithClickEvents: the scrim is a convenience; Esc is the real close
    <div className="scrim" onClick={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={input}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKey}
          placeholder="Search commands…"
          aria-label="Search commands"
          role="combobox"
          aria-expanded="true"
          aria-controls="cmdlist"
          aria-activedescendant={hits[i] ? `cmd-${hits[i].id}` : undefined}
        />
        <ul className="cmdlist" id="cmdlist" role="listbox">
          {hits.map((c, n) => (
            <li
              key={c.id}
              id={`cmd-${c.id}`}
              role="option"
              aria-selected={n === i}
              aria-disabled={c.disabled}
              className={`${n === i ? "on" : ""}${c.disabled ? " off" : ""}`}
              onMouseEnter={() => setI(n)}
              onClick={() => run(c)}
            >
              <span className="g">{c.group}</span>
              <span className="l">{c.label}</span>
              {c.hint && <span className="h">{c.hint}</span>}
            </li>
          ))}
          {!hits.length && <li className="none">No command matches “{q}”.</li>}
        </ul>
      </div>
    </div>
  );
}
