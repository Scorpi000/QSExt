/**
 * FactorDiscover - 因子发现抽屉
 *
 * 从 FactorDB 或 QSRegistry 双源浏览并添加因子到全局池。
 */

import { useState, useEffect, useCallback } from 'react'
import { Drawer, Tabs, Select, Input, List, Button, Tag, Space, message, Radio } from 'antd'
import { SearchOutlined, PlusOutlined } from '@ant-design/icons'
import type { Connection } from '../../services/connection'
import { getConnections } from '../../services/connection'
import type { FactorTable, FactorInfo } from '../../services/factor'
import { getTables, getFactors } from '../../services/factor'
import { searchFactors, semanticSearch } from '../../services/registry'
import type { FactorSearchResult } from '../../services/registry'
import { useFactorPoolStore } from '../../stores/factorPoolStore'
import type { PoolItem } from '../../types/pool'

interface FactorDiscoverProps {
  open: boolean
  onClose: () => void
}

function FactorDiscover({ open, onClose }: FactorDiscoverProps) {
  const addItems = useFactorPoolStore((s) => s.addItems)
  const existingItems = useFactorPoolStore((s) => s.items)

  // FactorDB 来源状态
  const [connections, setConnections] = useState<Connection[]>([])
  const [activeConnId, setActiveConnId] = useState<string | null>(null)
  const [tables, setTables] = useState<FactorTable[]>([])
  const [activeTable, setActiveTable] = useState<string | null>(null)
  const [factors, setFactors] = useState<FactorInfo[]>([])
  const [loading, setLoading] = useState(false)

  // QSRegistry 来源状态
  const [searchQuery, setSearchQuery] = useState('')
  const [searchMode, setSearchMode] = useState<'keyword' | 'semantic'>('keyword')
  const [searchResults, setSearchResults] = useState<FactorSearchResult[]>([])
  const [searching, setSearching] = useState(false)

  // 加载连接
  useEffect(() => {
    if (!open) return
    getConnections()
      .then((data) => setConnections(data as unknown as Connection[]))
      .catch(() => {})
  }, [open])

  // 加载表
  const handleConnChange = useCallback(async (connId: string) => {
    setActiveConnId(connId)
    setActiveTable(null)
    setFactors([])
    if (!connId) return
    setLoading(true)
    try {
      const data = await getTables(connId)
      setTables(data as unknown as FactorTable[])
    } catch {
      setTables([])
    } finally {
      setLoading(false)
    }
  }, [])

  // 加载因子
  const handleTableChange = useCallback(async (tableName: string) => {
    setActiveTable(tableName)
    if (!activeConnId) return
    setLoading(true)
    try {
      const data = await getFactors(activeConnId, tableName)
      setFactors(data as unknown as FactorInfo[])
    } catch {
      setFactors([])
    } finally {
      setLoading(false)
    }
  }, [activeConnId])

  // QSRegistry 搜索
  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) return
    setSearching(true)
    try {
      const data = searchMode === 'semantic'
        ? await semanticSearch(searchQuery)
        : await searchFactors(searchQuery)
      setSearchResults((data as unknown as FactorSearchResult[]) || [])
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }, [searchQuery, searchMode])

  // 添加因子到池
  const addToPool = (item: PoolItem) => {
    const existingIds = new Set(existingItems.map((i) => i.id))
    if (existingIds.has(item.id)) {
      message.warning('该因子已在池中')
      return
    }
    addItems([item])
    message.success(`已添加: ${item.label}`)
  }

  const existingIds = new Set(existingItems.map((i) => i.id))

  return (
    <Drawer
      title="添加因子到全局池"
      open={open}
      onClose={onClose}
      width={480}
    >
      <Tabs
        items={[
          {
            key: 'db',
            label: 'FactorDB',
            children: (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Select
                  placeholder="选择连接"
                  style={{ width: '100%' }}
                  value={activeConnId}
                  onChange={handleConnChange}
                  options={connections.map((c) => ({
                    value: c.qsid,
                    label: `${c.name} (${c.db_type})`,
                  }))}
                />
                <Select
                  placeholder="选择因子表"
                  style={{ width: '100%' }}
                  value={activeTable}
                  onChange={handleTableChange}
                  loading={loading}
                  options={tables.map((t) => ({ value: t.name, label: t.name }))}
                />
                <List
                  loading={loading}
                  size="small"
                  style={{ maxHeight: 360, overflow: 'auto' }}
                  dataSource={factors}
                  renderItem={(f: FactorInfo) => {
                    const poolId = `db:${activeConnId}:${activeTable}:${f.name}`
                    const inPool = existingIds.has(poolId)
                    return (
                      <List.Item
                        actions={[
                          <Button
                            key="add"
                            size="small"
                            type="primary"
                            icon={<PlusOutlined />}
                            disabled={inPool}
                            onClick={() =>
                              addToPool({
                                id: poolId,
                                qsid: '',
                                source: 'db',
                                label: f.name,
                                ref: {
                                  conn_id: activeConnId || '',
                                  table_name: activeTable || '',
                                  factor_name: f.name,
                                },
                              })
                            }
                          >
                            {inPool ? '已在池中' : '添加'}
                          </Button>,
                        ]}
                      >
                        <List.Item.Meta
                          title={f.name}
                          description={
                            <span>
                              <Tag>{f.data_type || 'unknown'}</Tag>
                              {f.description}
                            </span>
                          }
                        />
                      </List.Item>
                    )
                  }}
                />
              </Space>
            ),
          },
          {
            key: 'registry',
            label: 'QSRegistry',
            children: (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Radio.Group
                  value={searchMode}
                  onChange={(e) => setSearchMode(e.target.value)}
                  size="small"
                  optionType="button"
                >
                  <Radio.Button value="keyword">关键词</Radio.Button>
                  <Radio.Button value="semantic">语义搜索</Radio.Button>
                </Radio.Group>
                <Input.Search
                  placeholder={searchMode === 'semantic' ? '输入自然语言描述...' : '输入因子名称或关键词...'}
                  enterButton={<SearchOutlined />}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onSearch={handleSearch}
                  loading={searching}
                />
                <List
                  size="small"
                  style={{ maxHeight: 400, overflow: 'auto' }}
                  dataSource={searchResults}
                  renderItem={(r: FactorSearchResult) => {
                    const qsid = r.qsid || ''
                    const poolId = `registry:${qsid}`
                    const inPool = existingIds.has(poolId)
                    return (
                      <List.Item
                        actions={[
                          <Button
                            key="add"
                            size="small"
                            type="primary"
                            icon={<PlusOutlined />}
                            disabled={inPool}
                            onClick={() =>
                              addToPool({
                                id: poolId,
                                qsid,
                                source: 'registry',
                                label: r.name || qsid,
                                ref: {},
                              })
                            }
                          >
                            {inPool ? '已在池中' : '添加'}
                          </Button>,
                        ]}
                      >
                        <List.Item.Meta
                          title={r.name || qsid}
                          description={
                            <span>
                              <Tag color="blue">QSRegistry</Tag>
                              {r.factor_class && (
                                <Tag>{r.factor_class === 'DerivativeFactor' ? '衍生' : r.factor_class === 'AtomicFactor' ? '原子' : r.factor_class}</Tag>
                              )}
                              {r.operator_name && <Tag>{r.operator_name}</Tag>}
                              {r.similarity !== undefined && (
                                <Tag color="green">{Math.round(r.similarity * 100)}%</Tag>
                              )}
                            </span>
                          }
                        />
                      </List.Item>
                    )
                  }}
                />
              </Space>
            ),
          },
        ]}
      />
    </Drawer>
  )
}

export default FactorDiscover
