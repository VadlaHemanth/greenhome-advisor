import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

export class ErrorBoundary extends Component<
  { children: ReactNode; onReload?: () => void },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Deliberately no logging or telemetry: error details can include home input.
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main id="main" className="initial-state">
        <section className="connection-state card">
          <h1>Let’s reopen your home workspace</h1>
          <div className="notice error" role="alert">
            <p>
              The page could not display the current result. No replacement
              estimate has been invented.
            </p>
            <p>
              Reload to start again. Unsaved edits and the current local plan
              will be cleared.
            </p>
          </div>
          <button
            type="button"
            className="button primary"
            onClick={() =>
              this.props.onReload
                ? this.props.onReload()
                : window.location.reload()
            }
          >
            Reload workspace
          </button>
        </section>
      </main>
    );
  }
}
