/**
 * ErrorBoundary - React 错误边界
 *
 * 捕获子组件渲染时抛出的错误，展示友好的错误提示和重试按钮。
 * 防止单个页面崩溃导致整个应用白屏。
 */

import { Component } from 'react'
import { Result, Button } from 'antd'

interface ErrorBoundaryProps {
  children: React.ReactNode
  /** 自定义错误标题 */
  title?: string
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('[ErrorBoundary] 捕获到组件错误:', error, errorInfo)
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <Result
          status="error"
          title={this.props.title || '页面出错'}
          subTitle={this.state.error?.message || '组件渲染时发生未知错误'}
          extra={[
            <Button key="retry" type="primary" onClick={this.handleRetry}>
              重试
            </Button>,
            <Button key="refresh" onClick={() => window.location.reload()}>
              刷新页面
            </Button>,
          ]}
        />
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
