import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * Catches render-time errors in any child view so a single component crash
 * shows a graceful message instead of a blank white page. React has no hook
 * equivalent for error boundaries, so this stays a class component.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean; message: string }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, message: error?.message ?? "Something went wrong." };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface the stack in the console for debugging during the demo.
    console.error("CareRelay render error:", error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false, message: "" });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="mx-auto max-w-lg px-8 py-20 text-center">
          <div className="surface-3d rounded-2xl p-8">
            <h2 className="font-serif text-xl font-semibold text-ink-900">
              This view hit an unexpected error
            </h2>
            <p className="mt-2 text-sm text-ink-600">
              The rest of the console is still working. Try going back to the queue.
            </p>
            <p className="mt-3 break-words rounded-lg bg-ink-50 px-3 py-2 text-left font-mono text-[11px] text-ink-500">
              {this.state.message}
            </p>
            <div className="mt-5 flex justify-center gap-2">
              <button
                onClick={this.handleReset}
                className="rounded-xl border border-ink-200 bg-white px-4 py-2 text-sm font-semibold text-ink-700 hover:border-brand-300 hover:text-brand-700"
              >
                Try again
              </button>
              <a
                href="/queue"
                className="rounded-xl bg-gradient-to-b from-brand-600 to-brand-700 px-4 py-2 text-sm font-semibold text-white shadow-raised"
              >
                Back to queue
              </a>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
