/**
 * 因子工作台页面
 *
 * 布局：左侧搜索面板 | 中间 DAG 可视化 | 右侧详情面板
 * 顶部操作区：导入因子脚本、AI 辅助创建
 */

import { useState } from 'react'
import { Row, Col, Card, Button, Space, Segmented } from 'antd'
import { PlusOutlined, ImportOutlined, RobotOutlined } from '@ant-design/icons'
import FactorSearch from '../../components/FactorSearch'
import DAGViewer from '../../components/DAGViewer'
import FactorDetail from '../../components/FactorDetail'
import ImportFactorDialog from '../../components/ImportFactorDialog'
import AiFactorAssistant from '../../components/AiFactorAssistant'
import { useFactorWorkbenchStore } from '../../stores/factorWorkbench'

type ViewMode = 'dag' | 'detail'

function FactorWorkbench() {
  const [viewMode, setViewMode] = useState<ViewMode>('dag')
  const [importDialogOpen, setImportDialogOpen] = useState(false)
  const [aiAssistantOpen, setAiAssistantOpen] = useState(false)
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
            <Space>
              <Button
                size="small"
                icon={<ImportOutlined />}
                onClick={() => setImportDialogOpen(true)}
              >
                导入因子脚本
              </Button>
              <Button
                type="primary"
                size="small"
                icon={<RobotOutlined />}
                onClick={() => setAiAssistantOpen(true)}
              >
                AI 辅助创建
              </Button>
            </Space>
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

      {/* 导入因子脚本对话框 */}
      <ImportFactorDialog
        open={importDialogOpen}
        onClose={() => setImportDialogOpen(false)}
      />

      {/* AI 因子助手 */}
      <AiFactorAssistant
        open={aiAssistantOpen}
        onClose={() => setAiAssistantOpen(false)}
      />
    </Row>
  )
}

export default FactorWorkbench
