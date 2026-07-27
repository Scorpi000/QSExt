/**
 * 因子工作台页面
 *
 * 布局：左侧搜索面板 | 中间 DAG 可视化 | 右侧详情面板
 */

import { useState } from 'react'
import { Row, Col, Card, Button, Space, Segmented } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import FactorSearch from '../../components/FactorSearch'
import DAGViewer from '../../components/DAGViewer'
import FactorDetail from '../../components/FactorDetail'
import CreateFactorWizard from '../../components/CreateFactorWizard'
import { useFactorWorkbenchStore } from '../../stores/factorWorkbench'

type ViewMode = 'dag' | 'detail'

function FactorWorkbench() {
  const [viewMode, setViewMode] = useState<ViewMode>('dag')
  const [wizardOpen, setWizardOpen] = useState(false)
  const { selectedQSID } = useFactorWorkbenchStore()

  return (
    <Row gutter={16} style={{ height: 'calc(100vh - 160px)' }}>
      {/* 左侧：搜索 */}
      <Col span={6}>
        <Card
          title="因子搜索"
          size="small"
          style={{ height: '100%' }}
          bodyStyle={{ padding: 0, height: 'calc(100% - 46px)', overflow: 'auto' }}
        >
          <FactorSearch />
        </Card>
      </Col>

      {/* 中间：DAG / 详情 */}
      <Col span={12} style={{ height: '100%' }}>
        <Card
          size="small"
          style={{ height: '100%' }}
          title={
            <Space>
              <span>{viewMode === 'dag' ? '依赖关系图' : '因子详情'}</span>
              {selectedQSID && (
                <Segmented
                  size="small"
                  value={viewMode}
                  onChange={(v) => setViewMode(v as ViewMode)}
                  options={[
                    { label: 'DAG', value: 'dag' },
                    { label: '详情', value: 'detail' },
                  ]}
                />
              )}
            </Space>
          }
          extra={
            <Button
              type="primary"
              size="small"
              icon={<PlusOutlined />}
              onClick={() => setWizardOpen(true)}
            >
              创建衍生因子
            </Button>
          }
          bodyStyle={{ padding: 0, height: 'calc(100% - 46px)', overflow: 'auto' }}
        >
          {viewMode === 'dag' ? <DAGViewer /> : <FactorDetail />}
        </Card>
      </Col>

      {/* 右侧：详情（当中间是 DAG 时显示） */}
      {viewMode === 'dag' && (
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
      )}

      {/* 创建向导 */}
      <CreateFactorWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
      />
    </Row>
  )
}

export default FactorWorkbench
