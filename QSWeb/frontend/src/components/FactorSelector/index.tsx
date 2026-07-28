/**
 * FactorSelector - 因子选择器组件
 *
 * 支持 FactorDB 和 QSRegistry 两个来源，以 Tab 切换。
 */

import { useState, useEffect, useCallback } from 'react'
import { Select, Tag, Tabs, Input, List, Button } from 'antd'
import { CloseOutlined, SearchOutlined } from '@ant-design/icons'
import type { Connection } from '../../services/connection'
import { getConnections } from '../../services/connection'
import type { FactorTable, FactorInfo } from '../../services/factor'
import { getTables, getFactors } from '../../services/factor'
import { searchFactors } from '../../services/registry'
import type { FactorSearchResult } from '../../services/registry'
import type { FactorRef } from '../../services/backtest'

interface FactorSelectorProps {
  /** 已选因子列表 */
  selected: FactorRef[]
  /** 已选因子变更回调 */
  onChange: (factors: FactorRef[]) => void
}

function FactorSelector({ selected, onChange }: FactorSelectorProps) {
  // 连接列表
  const [connections, setConnections] = useState<Connection[]>([])
  const [loadingConns, setLoadingConns] = useState(false)

  // 选中的连接和表
  const [activeConnId, setActiveConnId] = useState<string | null>(null)
  const [tables, setTables] = useState<FactorTable[]>([])
  const [loadingTables, setLoadingTables] = useState(false)
  const [activeTable, setActiveTable] = useState<string | null>(null)

  // 因子列表
  const [factors, setFactors] = useState<FactorInfo[]>([])
  const [loadingFactors, setLoadingFactors] = useState(false)

  // ─── 加载连接 ─────────────────────────────────────────────

  const loadConnections = useCallback(async () => {
    setLoadingConns(true)
    try {
      const data = await getConnections()
      setConnections(data as unknown as Connection[])
    } catch {
      // 错误已在拦截器中处理
    } finally {
      setLoadingConns(false)
    }
  }, [])

  useEffect(() => {
    loadConnections()
  }, [loadConnections])

  // ─── 选连接 → 加载表 ──────────────────────────────────────

  const handleConnChange = async (connId: string) => {
    setActiveConnId(connId)
    setActiveTable(null)
    setFactors([])
    setLoadingTables(true)
    try {
      const data = await getTables(connId)
      setTables(data as unknown as FactorTable[])
    } catch {
      // handled
    } finally {
      setLoadingTables(false)
    }
  }

  // ─── 选表 → 加载因子 ──────────────────────────────────────

  const handleTableChange = async (tableName: string) => {
    if (!activeConnId) return
    setActiveTable(tableName)
    setLoadingFactors(true)
    try {
      const data = await getFactors(activeConnId, tableName)
      setFactors(data as unknown as FactorInfo[])
    } catch {
      // handled
    } finally {
      setLoadingFactors(false)
    }
  }

  // ─── 选择因子 ─────────────────────────────────────────────

  const handleFactorSelect = (factorName: string) => {
    if (!activeConnId || !activeTable) return
    const ref: FactorRef = {
      source: 'db',
      name: factorName,
      conn_id: activeConnId,
      table_name: activeTable,
    }
    // 去重
    const exists = selected.some(
      (f) => f.name === ref.name && f.conn_id === ref.conn_id && f.table_name === ref.table_name
    )
    if (!exists) {
      onChange([...selected, ref])
    }
  }

  const handleRemove = (ref: FactorRef) => {
    const key = (r: FactorRef) =>
      `${r.source}:${r.conn_id}:${r.table_name}:${r.name}`
    const targetKey = key(ref)
    onChange(selected.filter((r) => key(r) !== targetKey))
  }

  const factorRefKey = (ref: FactorRef) =>
    `${ref.source}:${ref.conn_id}:${ref.table_name}:${ref.name}`

  // ─── QSRegistry 搜索 ───────────────────────────────────────

  const [registryQuery, setRegistryQuery] = useState('')
  const [registryResults, setRegistryResults] = useState<FactorSearchResult[]>([])
  const [registryLoading, setRegistryLoading] = useState(false)

  const handleRegistrySearch = useCallback(async (query: string) => {
    setRegistryQuery(query)
    if (!query || query.trim().length === 0) {
      setRegistryResults([])
      return
    }
    setRegistryLoading(true)
    try {
      const data = await searchFactors(query.trim(), 20)
      setRegistryResults(data as unknown as FactorSearchResult[])
    } catch {
      // 错误已在拦截器中处理
    } finally {
      setRegistryLoading(false)
    }
  }, [])

  const handleRegistrySelect = (result: FactorSearchResult) => {
    const ref: FactorRef = {
      source: 'registry',
      name: result.qsid,  // 使用 QSID 作为引用名（后端通过 QSID 重建因子）
    }
    const exists = selected.some(
      (f) => f.source === 'registry' && f.name === ref.name
    )
    if (!exists) {
      onChange([...selected, ref])
    }
    setRegistryQuery('')
    setRegistryResults([])
  }

  // ─── FactorDB Tab ──────────────────────────────────────────

  const factorDbTab = (
    <div>
      <div style={{ marginBottom: 12 }}>
        <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>连接</div>
        <Select
          style={{ width: '100%' }}
          placeholder="选择因子库连接"
          loading={loadingConns}
          value={activeConnId}
          onChange={handleConnChange}
          options={connections.map((c) => ({
            value: c.id,
            label: `${c.name} (${c.db_type})`,
          }))}
        />
      </div>

      {activeConnId && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>因子表</div>
          <Select
            style={{ width: '100%' }}
            placeholder="选择因子表"
            loading={loadingTables}
            value={activeTable}
            onChange={handleTableChange}
            options={tables.map((t) => ({
              value: t.name,
              label: `${t.name} (${t.factor_count ?? '?'} 个因子)`,
            }))}
          />
        </div>
      )}

      {activeTable && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>因子</div>
          <Select
            style={{ width: '100%' }}
            placeholder="搜索并选择因子（支持搜索）"
            showSearch
            loading={loadingFactors}
            value={undefined}
            onChange={handleFactorSelect}
            filterOption={(input, option) =>
              (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
            }
            options={factors.map((f) => ({
              value: f.name,
              label: f.name,
            }))}
          />
        </div>
      )}

      {/* 已选因子 Tags */}
      <div>
        <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>
          已选因子 ({selected.length})
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {selected.length === 0 ? (
            <span style={{ color: '#ccc', fontSize: 12 }}>暂未选择</span>
          ) : (
            selected.map((ref) => (
              <Tag
                key={factorRefKey(ref)}
                closable
                onClose={() => handleRemove(ref)}
                closeIcon={<CloseOutlined />}
                color="blue"
              >
                {ref.name}
              </Tag>
            ))
          )}
        </div>
      </div>
    </div>
  )

  // ─── QSRegistry Tab ────────────────────────────────────────

  const registryTab = (
    <div>
      {/* 搜索框 */}
      <div style={{ marginBottom: 12 }}>
        <Input.Search
          placeholder="输入因子名称搜索 QSRegistry..."
          value={registryQuery}
          onChange={(e) => handleRegistrySearch(e.target.value)}
          loading={registryLoading}
          allowClear
          enterButton={<Button type="primary" icon={<SearchOutlined />}>搜索</Button>}
          onSearch={(val) => handleRegistrySearch(val)}
        />
      </div>

      {/* 搜索结果列表 */}
      {registryResults.length > 0 && (
        <div style={{ marginBottom: 12, maxHeight: 200, overflow: 'auto' }}>
          <List
            size="small"
            dataSource={registryResults}
            renderItem={(item) => (
              <List.Item
                style={{ cursor: 'pointer', padding: '6px 8px' }}
                onClick={() => handleRegistrySelect(item)}
                onMouseEnter={(e) => (e.currentTarget.style.background = '#f5f5f5')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <List.Item.Meta
                  title={
                    <span>
                      {item.name}
                      <span style={{ fontSize: 11, color: '#999', marginLeft: 8 }}>
                        {item.factor_class === 'DerivativeFactor' ? '衍生' : item.factor_class === 'DataFactor' ? '数据' : ''}
                      </span>
                    </span>
                  }
                  description={
                    <span style={{ fontSize: 11 }}>
                      <span style={{ color: '#888' }}>{item.qsid?.slice(0, 8)}</span>
                      {item.operator_name && (
                        <span style={{ color: '#aaa', marginLeft: 8 }}>{item.operator_name}</span>
                      )}
                    </span>
                  }
                />
              </List.Item>
            )}
          />
        </div>
      )}

      {/* 已选因子 Tags（含 registry 来源） */}
      <div>
        <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>
          已选因子 ({selected.length})
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {selected.length === 0 ? (
            <span style={{ color: '#ccc', fontSize: 12 }}>暂未选择</span>
          ) : (
            selected.map((ref) => (
              <Tag
                key={factorRefKey(ref)}
                closable
                onClose={() => handleRemove(ref)}
                closeIcon={<CloseOutlined />}
                color={ref.source === 'registry' ? 'purple' : 'blue'}
              >
                {ref.source === 'registry' ? `[R] ${ref.name?.slice(0, 10)}...` : ref.name}
              </Tag>
            ))
          )}
        </div>
      </div>
    </div>
  )

  return (
    <Tabs
      size="small"
      items={[
        { key: 'db', label: '因子库', children: factorDbTab },
        { key: 'registry', label: 'QSRegistry', children: registryTab },
      ]}
    />
  )
}

export default FactorSelector
