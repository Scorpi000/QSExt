/**
 * 因子工作台页面
 *
 * 布局：左侧搜索面板 | 中间 DAG 可视化 | 右侧详情面板
 * 顶部操作区：导入因子脚本
 * AI 助手通过全局 FAB / Ctrl+K 唤起（自动感知 /factor 路由使用 factor context）
 */

import { useState } from 'react'
import { Row, Col, Card, Button } from 'antd'
import { ImportOutlined } from '@ant-design/icons'
import FactorSearch from '../../components/FactorSearch'
import DAGViewer from '../../components/DAGViewer'
import FactorDetail from '../../components/FactorDetail'
import ImportFactorDialog from '../../components/ImportFactorDialog'

function FactorWorkbench() {
  const [importDialogOpen, setImportDialogOpen] = useState(false)

  return (
    <Row gutter={16} style={{ height: 'calc(100vh - 160px)' }}>
      {/* 左侧：搜索 */}
      <Col span={4}>
        <Card
          title="因子搜索"
          size="small"
          style={{ height: '100%' }}
          bodyStyle={{ padding: 0, height: 'calc(100% - 46px)', overflow: 'auto' }}
        >
          <FactorSearch />
        </Card>
      </Col>

      {/* 中间：DAG */}
      <Col span={14} style={{ height: '100%' }}>
        <Card
          size="small"
          title="依赖关系图"
          style={{ height: '100%' }}
          extra={
            <Button
              size="small"
              icon={<ImportOutlined />}
              onClick={() => setImportDialogOpen(true)}
            >
              导入因子脚本
            </Button>
          }
          bodyStyle={{ padding: 0, height: 'calc(100% - 46px)', overflow: 'auto' }}
        >
          <DAGViewer />
        </Card>
      </Col>

      {/* 右侧：详情 */}
      <Col span={6} style={{ height: '100%' }}>
        <Card
          title="因子详情"
          size="small"
          style={{ height: '100%' }}
          bodyStyle={{ padding: 0, height: 'calc(100% - 46px)', overflow: 'auto' }}
        >
          <FactorDetail />
        </Card>
      </Col>

      {/* 导入因子脚本对话框 */}
      <ImportFactorDialog
        open={importDialogOpen}
        onClose={() => setImportDialogOpen(false)}
      />
    </Row>
  )
}

export default FactorWorkbench
