/**
 * 策略回测结果展示 —— 复用 ResultTree + ResultLeaf 组件
 *
 * 左侧：结果树（按 type 区分图标）
 * 右侧：叶子节点详情（series→Plotly折线图+表格, dataframe→表格, scalar→数值）
 */
import React, { useState, useEffect, useCallback, useRef } from 'react'
import { Row, Col, Card, Spin, Empty } from 'antd'
import type { ResultNode } from '../../services/strategy'
import { getStrategyBacktestResult } from '../../services/strategy'
import ResultTree from '../../components/ResultTree'
import ResultLeaf from '../../components/ResultLeaf'

interface StrategyResultProps {
  taskId: string
  onResultReady?: () => void
}

const StrategyResult: React.FC<StrategyResultProps> = ({ taskId, onResultReady }) => {
  const [resultTree, setResultTree] = useState<ResultNode | null>(null)
  const [selectedLeaf, setSelectedLeaf] = useState<ResultNode | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval>>()

  const fetchResult = useCallback(async () => {
    try {
      const data = await getStrategyBacktestResult(taskId) as unknown as Record<string, any>
      // 202 状态下 axios 不会抛异常（2xx），需要检查是否有有效的 type 字段
      if (data && data.type) {
        setResultTree(data as unknown as ResultNode)
        setLoading(false)
        onResultReady?.()
        if (pollRef.current) {
          clearInterval(pollRef.current)
          pollRef.current = undefined
        }
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || '获取结果失败')
      setLoading(false)
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = undefined
      }
    }
  }, [taskId])

  useEffect(() => {
    setLoading(true)
    setError(null)
    setResultTree(null)
    setSelectedLeaf(null)

    fetchResult()
    pollRef.current = setInterval(fetchResult, 2000)

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
      }
    }
  }, [taskId, fetchResult])

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <Spin tip="回测运行中..." />
      </div>
    )
  }

  if (error) {
    return <Empty description={error} />
  }

  if (!resultTree) {
    return <Empty description="暂无结果" />
  }

  return (
    <Row gutter={8} style={{ height: 'calc(100vh - 280px)', minHeight: 400 }}>
      {/* 左侧：结果树 */}
      <Col span={8} style={{ height: '100%' }}>
        <Card
          title="结果树"
          size="small"
          style={{ height: '100%' }}
          bodyStyle={{ padding: 8, height: 'calc(100% - 46px)', overflow: 'auto' }}
        >
          <ResultTree data={resultTree as any} onSelect={setSelectedLeaf as any} />
        </Card>
      </Col>

      {/* 右侧：详情 */}
      <Col span={16} style={{ height: '100%' }}>
        <Card
          title={selectedLeaf ? selectedLeaf.label : '结果详情'}
          size="small"
          style={{ height: '100%' }}
          bodyStyle={{ padding: 12, height: 'calc(100% - 46px)', overflow: 'auto' }}
        >
          <ResultLeaf node={selectedLeaf as any} />
        </Card>
      </Col>
    </Row>
  )
}

export default StrategyResult
