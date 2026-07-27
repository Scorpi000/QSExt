/**
 * 因子搜索组件
 */

import { useState } from 'react'
import { Input, Button, Radio, List, Tag, Space, Spin, Empty, message } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import {
  searchFactors,
  semanticSearch,
  FactorSearchResult,
} from '../../services/registry'
import { useFactorWorkbenchStore } from '../../stores/factorWorkbench'

const { Search } = Input

function FactorSearch() {
  const [query, setQuery] = useState('')
  const {
    searchResults,
    searchMode,
    searching,
    setSearchMode,
    setSearchResults,
    setSearching,
    setSelectedQSID,
  } = useFactorWorkbenchStore()

  const handleSearch = async () => {
    if (!query.trim()) return
    setSearching(true)
    try {
      let results: FactorSearchResult[]
      if (searchMode === 'semantic') {
        results = (await semanticSearch(query.trim())) as unknown as FactorSearchResult[]
      } else {
        results = (await searchFactors(query.trim())) as unknown as FactorSearchResult[]
      }
      setSearchResults(results)
      if (results.length === 0) {
        message.info('未找到匹配的因子')
      }
    } catch {
      message.error('搜索失败')
    } finally {
      setSearching(false)
    }
  }

  const getFactorClassColor = (cls: string) => {
    const colors: Record<string, string> = {
      AtomicFactor: '#1890ff',
      DerivativeFactor: '#2f54eb',
    }
    return colors[cls] || '#666'
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '12px' }}>
        <Radio.Group
          value={searchMode}
          onChange={(e) => setSearchMode(e.target.value)}
          size="small"
          style={{ marginBottom: 8 }}
        >
          <Radio.Button value="keyword">关键词</Radio.Button>
          <Radio.Button value="semantic">语义搜索</Radio.Button>
        </Radio.Group>

        <Search
          placeholder={searchMode === 'semantic' ? '输入自然语言描述...' : '输入因子名称或关键词...'}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onSearch={handleSearch}
          enterButton={<SearchOutlined />}
          loading={searching}
          allowClear
        />
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        <Spin spinning={searching}>
          {searchResults.length > 0 ? (
            <List
              size="small"
              dataSource={searchResults}
              renderItem={(item) => (
                <List.Item
                  style={{ cursor: 'pointer', padding: '8px 12px' }}
                  onClick={() => setSelectedQSID(item.qsid)}
                >
                  <div style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 500, fontSize: 13 }}>{item.name}</span>
                      <Space size={4}>
                        <Tag color={getFactorClassColor(item.factor_class)} style={{ fontSize: 11 }}>
                          {item.factor_class === 'AtomicFactor' ? '原子' : '衍生'}
                        </Tag>
                        {item.operator_type && (
                          <Tag style={{ fontSize: 11 }}>{item.operator_type}</Tag>
                        )}
                      </Space>
                    </div>
                    <div style={{ fontSize: 11, color: '#888', marginTop: 2 }}>
                      {item.qsid}
                      {item.similarity !== undefined && (
                        <span style={{ marginLeft: 8 }}>
                          相似度: {(item.similarity * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  </div>
                </List.Item>
              )}
            />
          ) : (
            <Empty
              description="输入关键词搜索因子"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              style={{ padding: '40px 0' }}
            />
          )}
        </Spin>
      </div>
    </div>
  )
}

export default FactorSearch
