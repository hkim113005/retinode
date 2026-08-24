// A crash in one panel should cost that panel, not the whole instrument. Without a
// boundary React unmounts the entire tree on any render error: a white screen with
// the answer only in the console, which is the least useful failure mode for a tool
// someone is mid-decision in.
import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

type Props = { children: ReactNode; what: string };
type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // keep the stack in the console for whoever is debugging; the UI stays calm
    console.error(`${this.props.what} crashed:`, error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="card panel" role="alert">
        <h2>{this.props.what} stopped</h2>
        <p className="empty">
          Something went wrong rendering this panel, so it has been isolated rather than
          taking the rest of the app down. The details are in the browser console.
        </p>
        <pre className="crash">{error.message}</pre>
        <button className="btn ghost small" onClick={() => this.setState({ error: null })}>
          Try again
        </button>
      </div>
    );
  }
}
