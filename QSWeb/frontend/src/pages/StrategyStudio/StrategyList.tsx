/**
 * 策略列表组件 —— 搜索、展示和选择策略
 */
import React, { useState, useEffect, useCallback } from 'react'
import { Input, List, Button, Tag, Space, Typography, message, Popconfirm } from 'antd'
import {
  SearchOutlined,
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type { StrategySearchResult } from '../../services/strategy'
import { searchStrategies, deleteStrategy } from '../../services/strategy'

const { Text } = Typography

interface StrategyListProps {
  selectedQSID: string | null
  onSelect: (strategy: StrategySearchResult | null) => void
}

const StrategyList: React.FC<StrategyListProps> = ({ selectedQSID, onSelect }) => {
  const [strategies, setStrategies] = useState<StrategySearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [searchText, setSearchText] = useState('')

  // 加载策略列表
  const loadStrategies = useCallback(async () => {
    setLoading(true)
    try {
      const results = await searchStrategies({
        q: searchText || undefined,
        limit: 100,
      })
      setStrategies(results)
    } catch {
      // 后端不可用时静默处理
      setStrategies([])
    } finally {
      setLoading(false)
    }
  }, [searchText])

  useEffect(() => {
    loadStrategies()
  }, [loadStrategies])

  // 删除策略
  const handleDelete = useCallback(async (qsid: string, e?: React.MouseEvent) => {
    e?.stopPropagation()
    try {
      await deleteStrategy(qsid, true)
      message.success('策略已删除')
      if (selectedQSID === qsid) {
        onSelect(null)
      }
      loadStrategies()
    } catch {
      message.error('删除失败')
    }
  }, [selectedQSID, onSelect, loadStrategies])

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            placeholder="搜索策略..."
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onPressEnter={loadStrategies}
            allowClear
          />
        </Space.Compact>
      </div>

      <div style={{ marginBottom: 12, display: 'flex', gap: 8 }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          size="small"
          onClick={() => onSelect(null)}
        >
          新建策略
        </Button>
        <Button
          icon={<ReloadOutlined />}
          size="small"
          onClick={loadStrategies}
        >
          刷新
        </Button>
      </div>

      <List
        loading={loading}
        dataSource={strategies}
        locale={{ emptyText: '暂无策略，点击"新建策略"开始' }}
        renderItem={(item) => (
          <List.Item
            key={item.QSID}
            onClick={() => onSelect(item)}
            style={{
              cursor: 'pointer',
              padding: '8px 12px',
              borderRadius: 6,
              marginBottom: 4,
              background: selectedQSID === item.QSID ? '#e6f4ff' : undefined,
              border: selectedQSID === item.QSID ? '1px solid #91caff' : '1px solid transparent',
            }}
            actions={[
              <Popconfirm
                key="delete"
                title="确定删除此策略？"
                onConfirm={(e) => handleDelete(item.QSID, e as any)}
              >
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={(e) => e.stopPropagation()}
                />
              </Popconfirm>,
            ]}
          >
            <List.Item.Meta
              title={
                <Space>
                  <Text strong>{item.Name}</Text>
                  {item.Tags?.map((tag) => (
                    <Tag key={tag} color="blue" style={{ fontSize: 11 }}>
                      {tag}
                    </Tag>
                  ))}
                </Space>
              }
              description={
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {item.Author && `${item.Author} · `}
                    {item.Description?.slice(0, 60)}
                    {(item.Description?.length ?? 0) > 60 ? '...' : ''}
                  </Text>
                </div>
              }
            />
          </List.Item>
        )}
      />
    </div>
  )
}

export default StrategyList
