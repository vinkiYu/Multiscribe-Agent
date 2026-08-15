import { Component, type ErrorInfo, type ReactNode } from 'react'
import { CircleAlert, RefreshCw } from 'lucide-react'

interface ErrorBoundaryProps {
  children: ReactNode
  onError?: (message: string) => void
}

interface ErrorBoundaryState {
  hasError: boolean
  message: string
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, message: '' }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, message: error.message || '未知错误' }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    const message = error.message || '组件渲染异常'
    this.props.onError?.(message)
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error, info)
  }

  retry = (): void => {
    this.setState({ hasError: false, message: '' })
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <section className="state-panel state-error" role="alert">
          <CircleAlert />
          <h2>页面渲染出现异常</h2>
          <p>{this.state.message}</p>
          <button className="btn btn-primary" type="button" onClick={this.retry}>
            <RefreshCw /> 重新加载
          </button>
        </section>
      )
    }
    return this.props.children
  }
}