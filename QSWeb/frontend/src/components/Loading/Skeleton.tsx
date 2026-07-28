import { Skeleton as AntSkeleton, Card, Row, Col } from 'antd'

interface PageSkeletonProps {
  /** 是否显示 */
  loading?: boolean
  /** 子内容 */
  children?: React.ReactNode
}

/** 页面级骨架屏：Card + 段落占位 */
function PageSkeleton({ loading = true, children }: PageSkeletonProps) {
  if (!loading && children) {
    return <>{children}</>
  }

  return (
    <div style={{ padding: 24 }}>
      <Card>
        <AntSkeleton active paragraph={{ rows: 1 }} />
      </Card>
      <br />
      <Row gutter={16}>
        <Col span={12}>
          <Card title="加载中...">
            <AntSkeleton active paragraph={{ rows: 4 }} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="加载中...">
            <AntSkeleton active paragraph={{ rows: 4 }} />
          </Card>
        </Col>
      </Row>
    </div>
  )
}

/** 表格骨架屏 */
function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <Card>
      <AntSkeleton active title paragraph={{ rows }} />
    </Card>
  )
}

export { PageSkeleton, TableSkeleton }
