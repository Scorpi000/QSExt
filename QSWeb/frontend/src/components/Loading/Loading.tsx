import { Spin } from 'antd'

interface LoadingProps {
  tip?: string
  fullscreen?: boolean
}

/** 通用 Loading 组件，用于 Suspense fallback 和全局加载状态 */
function Loading({ tip = '加载中...', fullscreen = false }: LoadingProps) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: fullscreen ? '100vh' : '100%',
        minHeight: 200,
      }}
    >
      <Spin size="large" tip={tip}>
        <div style={{ padding: 50 }} />
      </Spin>
    </div>
  )
}

export default Loading
