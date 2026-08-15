// Top-level error boundary (item 4, docs/ROADMAP-NEXT.md).
//
// One panel/map/Canvas runtime crash used to blank the whole HUD.  This small
// boundary catches render/lifecycle errors in its subtree and renders a labeled
// fallback card instead, so a live demo stays on screen.  Used in two places:
//   - main.tsx wraps <App/> — any uncaught render crash shows the card rather
//     than a white screen;
//   - App.tsx wraps the hud-body (left/center/right) so a panel crash keeps the
//     header (brand + BHI) and footer (story controls) alive.
import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
  /** Short label shown in the fallback card, e.g. "main view". */
  label?: string
}

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[ErrorBoundary:${this.props.label ?? 'app'}]`, error, info)
  }

  private reset = (): void => {
    this.setState({ error: null })
  }

  render(): ReactNode {
    if (this.state.error === null) return this.props.children
    return (
      <div className="error-boundary-card" role="alert">
        <div className="error-boundary-title">Preview crashed — {this.props.label ?? 'app'}</div>
        <div className="error-boundary-msg">{String(this.state.error.message ?? this.state.error)}</div>
        <button className="error-boundary-reset" onClick={this.reset}>
          Try again
        </button>
      </div>
    )
  }
}
