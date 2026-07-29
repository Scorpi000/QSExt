/**
 * FactorPoolPanel - 全局因子池面板
 *
 * 展示池中所有因子，支持选中/取消、移除操作。
 * 嵌入各页面，读写同一个 Zustand store。
 */

import { Button, List, Tag, Tooltip, Space, Empty } from 'antd'
import { DeleteOutlined, PlusOutlined, CheckCircleOutlined } from '@ant-design/icons'
import { useFactorPoolStore } from '../../stores/factorPoolStore'
import type { PoolItem } from '../../types/pool'

interface FactorPoolPanelProps {
  /** 显示"添加因子"按钮并触发回调 */
  onAddClick?: () => void
  /** 紧凑模式（显示更少信息） */
  compact?: boolean
}

function FactorPoolPanel({ onAddClick, compact = false }: FactorPoolPanelProps) {
  const items = useFactorPoolStore((s) => s.items)
  const selectedIds = useFactorPoolStore((s) => s.selectedIds)
  const removeItem = useFactorPoolStore((s) => s.removeItem)
  const toggleSelect = useFactorPoolStore((s) => s.toggleSelect)

  const sourceColor = (source: string) => (source === 'registry' ? 'blue' : 'green')
  const sourceLabel = (source: string) => (source === 'registry' ? '注册中心' : '因子库')

  if (items.length === 0) {
    return (
      <Empty
        description="因子池为空"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        style={{ marginTop: 16 }}
      >
        {onAddClick && (
          <Button type="primary" icon={<PlusOutlined />} onClick={onAddClick}>
            添加因子到池
          </Button>
        )}
      </Empty>
    )
  }

  return (
    <div>
      <Space style={{ marginBottom: 8, width: '100%', justifyContent: 'space-between' }}>
        <span style={{ color: '#666', fontSize: 13 }}>
          {items.length} 个因子
          {selectedIds.size > 0 && `（已选 ${selectedIds.size}）`}
        </span>
        {onAddClick && (
          <Button size="small" icon={<PlusOutlined />} onClick={onAddClick}>
            添加
          </Button>
        )}
      </Space>

      <List
        size="small"
        dataSource={items}
        style={{ maxHeight: compact ? 200 : 400, overflow: 'auto' }}
        renderItem={(item: PoolItem) => {
          const isSelected = selectedIds.has(item.id)
          return (
            <List.Item
              key={item.id}
              style={{
                cursor: 'pointer',
                background: isSelected ? '#e6f4ff' : undefined,
                padding: '4px 8px',
              }}
              onClick={() => toggleSelect(item.id)}
              actions={[
                <Tooltip title="从池中移除" key="remove">
                  <Button
                    size="small"
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={(e) => {
                      e.stopPropagation()
                      removeItem(item.id)
                    }}
                  />
                </Tooltip>,
              ]}
            >
              <List.Item.Meta
                avatar={
                  isSelected ? (
                    <CheckCircleOutlined style={{ color: '#1677ff', fontSize: 16 }} />
                  ) : (
                    <span style={{ width: 16, display: 'inline-block' }} />
                  )
                }
                title={
                  <span style={{ fontSize: 13 }}>
                    {item.label}
                    <Tag
                      color={sourceColor(item.source)}
                      style={{ marginLeft: 6, fontSize: 10, lineHeight: '16px' }}
                    >
                      {sourceLabel(item.source)}
                    </Tag>
                  </span>
                }
                description={
                  !compact && item.ref.table_name ? (
                    <span style={{ fontSize: 11, color: '#999' }}>
                      {item.ref.table_name}.{item.ref.factor_name}
                    </span>
                  ) : undefined
                }
              />
            </List.Item>
          )
        }}
      />
    </div>
  )
}

export default FactorPoolPanel
